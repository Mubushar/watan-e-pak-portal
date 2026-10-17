import {
  BookOpen,
  Calculator,
  CalendarClock,
  CalendarDays,
  Camera,
  Crosshair,
  DraftingCompass,
  FileChartColumn,
  FileJson,
  FileText,
  Flag,
  Frame,
  HandCoins,
  HardHat,
  Hexagon,
  Landmark,
  Map as MapIcon,
  MapPin,
  Percent,
  Receipt,
  Ruler,
  Satellite,
  Scale,
  Stamp,
  Tag,
  TrendingUp,
  Users,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";

/** A Tools Center card from `/tools/catalog`. */
export interface ToolCard {
  key: string;
  name: string;
  category: string;
  phase: number;
  blurb: string;
  mcp_tool?: string | null;
}

export const TOOL_ICON: Record<string, LucideIcon> = {
  mortgage: Landmark,
  installment: CalendarClock,
  rental_yield: Percent,
  appreciation: TrendingUp,
  area: Ruler,
  price_per_unit: Tag,
  plot_dimensions: Frame,
  construction: HardHat,
  transfer: Stamp,
  commission: HandCoins,
  cgt: Receipt,
  joint_investment: Users,
  rent_vs_buy: Scale,
  georeference: Crosshair,
  map_measure: Ruler,
  coords_area: Hexagon,
  geodata: FileJson,
  aerial: Satellite,
  nearby: MapPin,
  cad: DraftingCompass,
  photo: Camera,
  documents: FileText,
  brochure: BookOpen,
  calendar: CalendarDays,
  milestones: Flag,
  reports: FileChartColumn,
};

export const CATEGORY_ICON: Record<string, LucideIcon> = {
  calculators: Calculator,
  gis: MapIcon,
  cad: DraftingCompass,
  photo: Camera,
  documents: FileText,
  calendar: CalendarDays,
};

/** Accent gradient per category for icon tiles. */
export const CATEGORY_ACCENT: Record<string, string> = {
  calculators: "from-brand-600 to-brand-400",
  gis: "from-sky-600 to-cyan-400",
  cad: "from-violet-600 to-fuchsia-400",
  photo: "from-rose-500 to-orange-400",
  documents: "from-slate-600 to-slate-400",
  calendar: "from-gold-600 to-gold-300",
};

/** Tools with a dedicated interactive calculator on /tools/:key. */
export const INTERACTIVE_TOOLS = new Set([
  "mortgage",
  "installment",
  "rental_yield",
  "appreciation",
  "area",
  "price_per_unit",
  "plot_dimensions",
  "construction",
  "transfer",
  "commission",
  "cgt",
  "joint_investment",
  "rent_vs_buy",
  "calendar",
  "map_measure",
  "coords_area",
]);

/** Extra calculators that exist on the backend but are not in the catalogue. */
export const EXTRA_TOOLS: ToolCard[] = [
  { key: "rent_vs_buy", name: "Rent vs Buy", category: "calculators", phase: 1, blurb: "Compare buying with a mortgage against renting over a holding period.", mcp_tool: "tool_rent_vs_buy" },
];

export function ToolIcon({ toolKey, category, className, size = "md" }: { toolKey: string; category?: string; className?: string; size?: "sm" | "md" | "lg" }) {
  const I = TOOL_ICON[toolKey] ?? CATEGORY_ICON[category ?? ""] ?? Wrench;
  const box = { sm: "h-8 w-8 rounded-lg", md: "h-11 w-11 rounded-xl", lg: "h-14 w-14 rounded-2xl" }[size];
  const ic = { sm: "h-4 w-4", md: "h-5 w-5", lg: "h-7 w-7" }[size];
  return (
    <span className={cn("inline-flex shrink-0 items-center justify-center bg-gradient-to-br text-white shadow-soft", CATEGORY_ACCENT[category ?? ""] ?? "from-brand-600 to-brand-400", box, className)}>
      <I className={ic} />
    </span>
  );
}

export function phaseTone(phase?: number) {
  return phase === 1 ? "green" : phase === 2 ? "gold" : "purple";
}
