/**
 * Big project inventories (hundreds of near-identical units) are shown as ONE summary card per
 * unit type — "Goldcrest Breeze Overseas · 2-bed apartment: 96 available, 5.2–5.8 marla, levels
 * 3–28, PKR 2.9–3.6 crore" — instead of one card per unit. The units themselves are one click away
 * (/properties?project=<id>&unit_type=<type>).
 *
 * Unit listings are written by backend/project_inventory.py with the title
 * "<project> — <unit type> <unit code> · <floor>", which is what the helpers below read.
 */
import type { Property } from "@/types";
import { pkrShort } from "@/lib/format";

export interface UnitGroup {
  kind: "group";
  key: string;
  projectId: string;
  projectName: string;
  unitType: string;
  units: Property[];
  /** Available units of this project in the list (all types). */
  projectTotal: number;
  priceMin: number;
  priceMax: number;
  sqftMin: number | null;
  sqftMax: number | null;
  marlaMin: number | null;
  marlaMax: number | null;
  floors: string;
}

export function projectNameOf(p: Property): string {
  return p.title.split(" — ")[0] || p.sector || "New project";
}

/** "3-bed apartment", "Shop", "Clinic" … from "<project> — 3-bed apartment 9F28 · Level 28". */
export function unitTypeOf(p: Property): string {
  const rest = p.title.split(" — ")[1] ?? "";
  const label = rest.split(" · ")[0] ?? "";
  const code = p.project_unit ?? "";
  const t = code && label.endsWith(` ${code}`) ? label.slice(0, -code.length - 1) : label.replace(/\s+\S+$/, "");
  return (t || p.category || "Unit").trim();
}

export function floorOf(p: Property): string | null {
  return p.title.split(" · ")[1]?.trim() || null;
}

/** A floor label as a sortable level: "Lower ground" -1, "Ground floor" 0, "Level 28" / "2nd floor" -> 28 / 2. */
function level(label: string): number | null {
  const l = label.toLowerCase();
  if (l.includes("lower ground")) return -1;
  if (l.startsWith("ground")) return 0;
  const m = l.match(/(\d+)/);
  return m ? Number(m[1]) : null;
}

const ordinal = (n: number) => (n === -1 ? "Lower ground" : n === 0 ? "Ground" : `${n}${["th", "st", "nd", "rd"][n % 100 > 10 && n % 100 < 14 ? 0 : n % 10 < 4 ? n % 10 : 0]}`);

function floorsSummary(labels: string[]): string {
  const uniq = [...new Set(labels)];
  if (!uniq.length) return "";
  const levels = uniq.map(level);
  if (levels.every((x) => x !== null)) {
    const nums = (levels as number[]).sort((a, b) => a - b);
    const lo = nums[0]!;
    const hi = nums[nums.length - 1]!;
    if (lo === hi) return uniq[0]!;
    return `${ordinal(lo)} – ${ordinal(hi)} floor · ${uniq.length} floors`;
  }
  return uniq.length <= 2 ? uniq.join(", ") : `${uniq.slice(0, 2).join(", ")} +${uniq.length - 2} more`;
}

const range = (xs: number[]): [number, number] | [null, null] => (xs.length ? [Math.min(...xs), Math.max(...xs)] : [null, null]);

/**
 * Replace each project's units with one group per unit type, placed where its first unit was
 * (so the portal's order is kept). A type with a single unit stays a normal listing.
 */
export function groupProjectUnits(list: Property[]): (Property | UnitGroup)[] {
  const byKey = new Map<string, Property[]>();
  const perProject = new Map<string, number>();
  for (const p of list) {
    if (!p.project_id) continue;
    const key = `${p.project_id}::${unitTypeOf(p)}`;
    byKey.set(key, [...(byKey.get(key) ?? []), p]);
    perProject.set(p.project_id, (perProject.get(p.project_id) ?? 0) + 1);
  }
  const out: (Property | UnitGroup)[] = [];
  const placed = new Set<string>();
  for (const p of list) {
    if (!p.project_id) {
      out.push(p);
      continue;
    }
    const key = `${p.project_id}::${unitTypeOf(p)}`;
    const units = byKey.get(key)!;
    if (units.length === 1) {
      out.push(p);
      continue;
    }
    if (placed.has(key)) continue;
    placed.add(key);
    const prices = units.map((u) => u.price);
    const [sqftMin, sqftMax] = range(units.map((u) => u.total_area ?? 0).filter(Boolean));
    const [marlaMin, marlaMax] = range(units.map((u) => u.marla_area ?? 0).filter(Boolean));
    out.push({
      kind: "group",
      key,
      projectId: p.project_id,
      projectName: projectNameOf(p),
      unitType: unitTypeOf(p),
      units,
      projectTotal: perProject.get(p.project_id) ?? units.length,
      priceMin: Math.min(...prices),
      priceMax: Math.max(...prices),
      sqftMin,
      sqftMax,
      marlaMin,
      marlaMax,
      floors: floorsSummary(units.map(floorOf).filter((x): x is string => !!x)),
    });
  }
  return out;
}

export const isGroup = (x: Property | UnitGroup): x is UnitGroup => (x as UnitGroup).kind === "group";

/** "PKR 3.25 – 6.3 Crore" (one unit), "PKR 85 Lakh – 1.2 Crore" (two), or a single price. */
export function priceRange(lo: number, hi: number): string {
  if (lo === hi) return pkrShort(lo);
  const a = pkrShort(lo, false);
  const b = pkrShort(hi, false);
  const [na, ...ua] = a.split(" ");
  const [nb, ...ub] = b.split(" ");
  return ua.join(" ") === ub.join(" ") ? `PKR ${na} – ${nb} ${ub.join(" ")}`.trim() : `PKR ${a} – ${b}`;
}
