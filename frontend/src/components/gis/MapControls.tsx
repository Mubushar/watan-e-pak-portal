/**
 * The map explorer's control column, grouped like a GIS toolbar:
 *   Map    base map · layers (one panel with an on/off switch for every layer) · label language
 *   View   pan (hand: normal map dragging) · fit to listings (full) · last view (back to where the
 *          map was before the last move or zoom) · box zoom in / out
 *          (each box tool stays on until clicked again or another tool is picked)
 *   Study  draw a case-study area (circle / rectangle / polygon)
 * The admin Edit tools sit apart, in a horizontal bar (EditBar) at the bottom left.
 *
 * The layers panel: a filter box, "All on / All off", then collapsible sections (Portal data,
 * Points of interest, Reference, DHA / Bahria / society master plans, GIS layers). Each section has a master switch
 * and shows how many of its layers are on; items can have sub-layers (e.g. a plan's labels).
 */
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Building2, LocateFixed, MapPin, Milestone, PencilLine, Plus, Spline, Square } from "lucide-react";
import type { EditMode, EditRights } from "./GeoEditor";
import { Check, ChevronDown, Circle, Globe, Hand, Undo2, Hexagon, Languages, Layers, Layers3, PencilRuler, RectangleHorizontal, Ruler, Search, Spline as SplineIcon, X, ZoomIn, ZoomOut, type LucideIcon } from "lucide-react";
import type { DrawMode } from "./AreaDraw";
import type { MapLang } from "./PakistanLayers";
import { BASE_MAPS, type BaseMapKey } from "@/components/map/PortalMap";
import { cn } from "@/lib/utils";

export interface LayerItem {
  key: string;
  label: string;
  hint?: string;
  icon?: LucideIcon;
  /** A colour swatch instead of an icon (category layers). */
  color?: string;
  on: boolean;
  onChange: (on: boolean) => void;
  /** Sub-layers, listed under the item when it's expanded. */
  children?: LayerItem[];
}
export interface LayerGroup {
  key: string;
  title: string;
  icon: LucideIcon;
  items: LayerItem[];
  /** A short note under the section (e.g. "zoom in to see …"). */
  note?: ReactNode;
}

const flat = (items: LayerItem[]): LayerItem[] => items.flatMap((i) => [i, ...(i.children ?? [])]);

/** A compact on/off switch. */
function Switch({ on, onChange, label, small }: { on: boolean; onChange: (v: boolean) => void; label: string; small?: boolean }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      onClick={(e) => {
        e.stopPropagation();
        onChange(!on);
      }}
      className={cn("relative shrink-0 rounded-full transition", small ? "h-4 w-7" : "h-5 w-9", on ? "bg-brand-600" : "bg-black/15 dark:bg-white/15")}
    >
      <span className={cn("absolute top-0.5 rounded-full bg-white shadow transition-all", small ? "h-3 w-3" : "h-4 w-4", on ? (small ? "start-[14px]" : "start-[18px]") : "start-0.5")} />
    </button>
  );
}

function Btn({
  icon: Icon,
  title,
  active,
  onClick,
  badge,
  text,
  iconClass,
  disabled,
}: {
  icon: LucideIcon;
  title: string;
  active?: boolean;
  disabled?: boolean;
  onClick: () => void;
  badge?: number;
  /** A short caption under the icon. */
  text?: string;
  /** Icon colour / fill when the button is not active. */
  iconClass?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      aria-label={title}
      aria-pressed={active}
      className={cn(
        "relative flex w-10 flex-col items-center justify-center transition first:rounded-t-xl last:rounded-b-xl disabled:cursor-default disabled:opacity-40 disabled:hover:bg-transparent",
        // Short screens: icons only, so the rail ends above the map's +/− zoom buttons.
        text ? "h-12 gap-0.5 [@media(max-height:940px)]:h-10" : "h-10",
        active ? "bg-brand-700 text-white" : "text-brand-800 hover:bg-brand-50 dark:text-white dark:hover:bg-white/10",
      )}
    >
      <Icon className={cn("h-[18px] w-[18px]", !active && iconClass)} />
      {text && <span className="text-[9px] font-bold leading-none [@media(max-height:940px)]:hidden">{text}</span>}
      {!!badge && <span className="absolute -end-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-gold-500 px-1 text-[10px] font-bold text-brand-950">{badge}</span>}
    </button>
  );
}

function ToolGroup({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-1 [@media(max-height:940px)]:gap-0.5">
      <span className="rounded-full bg-white/90 px-1.5 text-[9px] font-bold uppercase tracking-wider text-ink-mute shadow-sm dark:bg-brand-950/90 [@media(max-height:760px)]:hidden">{label}</span>
      <div className="flex flex-col divide-y divide-black/5 rounded-xl bg-white shadow-soft ring-1 ring-black/5 dark:divide-white/10 dark:bg-brand-950">{children}</div>
    </div>
  );
}

function Popover({ title, onClose, children, wide }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  return (
    <div className={cn("absolute end-[3.25rem] top-0 flex max-h-[calc(100dvh-12rem)] flex-col overflow-hidden rounded-2xl bg-white shadow-2xl ring-1 ring-black/5 dark:bg-brand-950", wide ? "w-80" : "w-60", "max-w-[calc(100vw-5rem)]")}>
      <div className="flex items-center justify-between border-b border-black/5 px-4 py-2.5 dark:border-white/10">
        <p className="text-sm font-semibold">{title}</p>
        <button type="button" onClick={onClose} className="btn btn-ghost btn-icon h-7 w-7" aria-label="Close">
          <X className="h-4 w-4" />
        </button>
      </div>
      {children}
    </div>
  );
}

function ItemRow({ item, depth = 0, forceOpen }: { item: LayerItem; depth?: number; forceOpen?: boolean }) {
  const [open, setOpen] = useState(false);
  const expanded = forceOpen || open;
  const Icon = item.icon;
  return (
    <>
      <div
        className={cn("flex items-center gap-2.5 rounded-lg py-1.5 pe-1 hover:bg-brand-50/70 dark:hover:bg-white/5", depth ? "ps-9" : "ps-2")}
        onClick={() => item.onChange(!item.on)}
        role="presentation"
      >
        {item.color ? (
          <span className={cn("h-3 w-3 shrink-0 rounded-full ring-2 ring-white dark:ring-brand-950", !item.on && "opacity-40")} style={{ background: item.color }} />
        ) : Icon ? (
          <span className={cn("flex h-7 w-7 shrink-0 items-center justify-center rounded-lg", item.on ? "bg-brand-700 text-white" : "bg-black/5 text-ink-soft dark:bg-white/10 dark:text-slate-300")}>
            <Icon className="h-3.5 w-3.5" />
          </span>
        ) : null}
        <span className="min-w-0 flex-1 cursor-pointer select-none">
          <span className={cn("block truncate", depth ? "text-xs" : "text-sm font-medium")}>{item.label}</span>
          {item.hint && !depth && <span className="block truncate text-[11px] text-ink-mute">{item.hint}</span>}
        </span>
        {!!item.children?.length && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setOpen((o) => !o);
            }}
            className="flex items-center gap-0.5 rounded-md px-1 text-[10px] font-semibold text-ink-mute hover:bg-black/5 dark:hover:bg-white/10"
            aria-label={expanded ? "Hide sub-layers" : "Show sub-layers"}
          >
            {item.children.filter((c) => c.on).length}/{item.children.length}
            <ChevronDown className={cn("h-3 w-3 transition", expanded && "rotate-180")} />
          </button>
        )}
        <Switch on={item.on} onChange={item.onChange} label={item.label} small={!!depth} />
      </div>
      {expanded && item.children?.map((c) => <ItemRow key={c.key} item={c} depth={depth + 1} />)}
    </>
  );
}

function Section({ group, filter, collapsed, onToggleCollapsed }: { group: LayerGroup; filter: string; collapsed: boolean; onToggleCollapsed: () => void }) {
  const f = filter.trim().toLowerCase();
  const items = useMemo(() => {
    if (!f) return group.items;
    return group.items
      .map((i) => {
        const kids = (i.children ?? []).filter((c) => c.label.toLowerCase().includes(f));
        return i.label.toLowerCase().includes(f) || kids.length ? { ...i, children: i.label.toLowerCase().includes(f) ? i.children : kids } : null;
      })
      .filter(Boolean) as LayerItem[];
  }, [group.items, f]);
  if (!items.length) return null;
  const all = flat(group.items);
  const onCount = group.items.filter((i) => i.on).length;
  const anyOn = all.some((i) => i.on);
  const Icon = group.icon;
  const open = !!f || !collapsed;
  return (
    <div className="border-b border-black/5 last:border-0 dark:border-white/10">
      <div className="flex items-center gap-2 px-3 py-2.5">
        <button type="button" onClick={onToggleCollapsed} className="flex min-w-0 flex-1 items-center gap-2 text-start" aria-expanded={open}>
          <ChevronDown className={cn("h-4 w-4 shrink-0 text-ink-mute transition", !open && "-rotate-90")} />
          <Icon className="h-4 w-4 shrink-0 text-brand-600 dark:text-brand-300" />
          <span className="truncate text-xs font-bold uppercase tracking-wider">{group.title}</span>
          <span className={cn("rounded-full px-1.5 text-[10px] font-bold", onCount ? "bg-brand-100 text-brand-800 dark:bg-brand-500/20 dark:text-brand-100" : "bg-black/5 text-ink-mute dark:bg-white/10")}>
            {onCount}/{group.items.length}
          </span>
        </button>
        <Switch
          on={anyOn}
          label={`${anyOn ? "Turn off" : "Turn on"} all ${group.title}`}
          onChange={(v) => group.items.forEach((i) => i.on !== v && i.onChange(v))}
        />
      </div>
      {open && (
        <div className="px-1 pb-2">
          {items.map((i) => (
            <ItemRow key={i.key} item={i} forceOpen={!!f && !!i.children?.length} />
          ))}
          {group.note && <p className="px-2 pt-1 text-[11px] text-ink-mute">{group.note}</p>}
        </div>
      )}
    </div>
  );
}

function readCollapsed(): Record<string, boolean> {
  try {
    return JSON.parse(localStorage.getItem("arz-map-layer-sections") ?? "{}");
  } catch {
    return {};
  }
}

export function MapControls({
  groups,
  base,
  onBase,
  onFit,
  onLastView,
  lastViewReady,
  zoomMode,
  onZoomMode,
  panActive,
  onPan,
  lang,
  onLang,
  drawMode,
  onDraw,
  measureMode,
  onMeasure,
}: {
  drawMode?: DrawMode | null;
  onDraw?: (m: DrawMode | null) => void;
  /** Measure tool: a distance or an area, or off. */
  measureMode?: "distance" | "area" | null;
  onMeasure?: (m: "distance" | "area" | null) => void;
  lang: MapLang;
  onLang: (l: MapLang) => void;
  groups: LayerGroup[];
  base: BaseMapKey;
  onBase: (b: BaseMapKey) => void;
  onFit?: () => void;
  /** Back to the previous map view (centre + zoom); `lastViewReady` is false until there is one. */
  onLastView?: () => void;
  lastViewReady?: boolean;
  /** Box zoom tool: "in", "out", or off (null). */
  zoomMode: "in" | "out" | null;
  onZoomMode: (m: "in" | "out" | null) => void;
  /** True when no tool is on and the map drags normally. */
  panActive: boolean;
  /** Switch every tool off: back to dragging the map. */
  onPan: () => void;
}) {
  const [open, setOpen] = useState<"base" | "layers" | "lang" | "draw" | "measure" | null>(null);
  const [filter, setFilter] = useState("");
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>(readCollapsed);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: PointerEvent) => !ref.current?.contains(e.target as Node) && setOpen(null);
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);
  const toggleSection = (k: string) =>
    setCollapsed((c) => {
      const n = { ...c, [k]: !c[k] };
      try {
        localStorage.setItem("arz-map-layer-sections", JSON.stringify(n));
      } catch {
        /* private mode */
      }
      return n;
    });
  const all = groups.flatMap((g) => g.items);
  const activeCount = all.filter((i) => i.on).length;
  const setAll = (v: boolean) => groups.forEach((g) => g.items.forEach((i) => i.on !== v && i.onChange(v)));
  // Using any other tool switches the zoom tool off.
  const other = (fn: () => void) => () => {
    if (zoomMode) onZoomMode(null);
    fn();
  };

  return (
    <div ref={ref} className="absolute end-3 top-3 z-[400] flex flex-col items-end gap-2">
      <ToolGroup label="Map">
        <Btn icon={Layers} text="Base" title="Base map" active={open === "base"} onClick={other(() => setOpen(open === "base" ? null : "base"))} />
        <Btn
          icon={Layers3}
          text="Portal"
          iconClass="text-emerald-600 fill-emerald-400/40 dark:text-emerald-400"
          title="Layers — turn any layer on or off"
          active={open === "layers"}
          badge={activeCount}
          onClick={other(() => setOpen(open === "layers" ? null : "layers"))}
        />
        <Btn icon={Languages} text="Lang" title="Map label language — English / اردو" active={open === "lang"} onClick={other(() => setOpen(open === "lang" ? null : "lang"))} />
      </ToolGroup>
      <ToolGroup label="View">
        <Btn icon={Hand} text="Pan" title="Pan: drag the map (turns every tool off)" active={panActive} onClick={onPan} />
        {onFit && <Btn icon={Globe} text="Full" title="Fit to listings" onClick={other(onFit)} />}
        {onLastView && (
          <Btn icon={Undo2} text="Last" title={lastViewReady ? "Last view: back to where the map was before" : "Last view: nothing to go back to yet"} disabled={!lastViewReady} onClick={other(onLastView)} />
        )}
        <Btn
          icon={ZoomIn}
          text="Zoom +"
          title={zoomMode === "in" ? "Box zoom-in is on — click to turn it off" : "Box zoom-in: drag a box to zoom in to it (stays on until you click again)"}
          active={zoomMode === "in"}
          onClick={() => onZoomMode(zoomMode === "in" ? null : "in")}
        />
        <Btn
          icon={ZoomOut}
          text="Zoom −"
          title={zoomMode === "out" ? "Box zoom-out is on — click to turn it off" : "Box zoom-out: drag a box — the current view shrinks into it (stays on until you click again)"}
          active={zoomMode === "out"}
          onClick={() => onZoomMode(zoomMode === "out" ? null : "out")}
        />
      </ToolGroup>
      {onDraw && (
        <ToolGroup label="Study">
          <Btn
            icon={PencilRuler}
            text="Select"
            title={drawMode ? "Cancel drawing" : "Draw a study area — circle, rectangle or polygon — for a case-study report"}
            active={!!drawMode || open === "draw"}
            onClick={other(() => (drawMode ? onDraw(null) : setOpen(open === "draw" ? null : "draw")))}
          />
          {onMeasure && (
            <Btn
              icon={Ruler}
              text="Measure"
              title={measureMode ? "Stop measuring" : "Measure a distance or an area on the map"}
              active={!!measureMode || open === "measure"}
              onClick={other(() => (measureMode ? onMeasure(null) : setOpen(open === "measure" ? null : "measure")))}
            />
          )}
        </ToolGroup>
      )}

      {open === "measure" && onMeasure && (
        <Popover title="Measure" onClose={() => setOpen(null)} wide>
          <div className="p-2">
            {(
              [
                ["distance", SplineIcon, "Distance", "Click points along the way; double-click or Enter to finish"],
                ["area", Hexagon, "Area", "Click each corner; double-click or Enter to finish — in m², marla, kanal, acres"],
              ] as ["distance" | "area", LucideIcon, string, string][]
            ).map(([k, Icon, l, hint]) => (
              <button
                key={k}
                type="button"
                onClick={() => {
                  onMeasure(k);
                  setOpen(null);
                }}
                className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-start hover:bg-brand-50 dark:hover:bg-white/10"
              >
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-amber-500/15 text-amber-700 dark:text-amber-300">
                  <Icon className="h-4 w-4" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-semibold">{l}</span>
                  <span className="block text-[11px] text-ink-mute">{hint}</span>
                </span>
              </button>
            ))}
            <p className="px-3 pt-1 text-[10px] text-ink-mute">The result can go to the AI assistant, or be saved as a PDF or a picture.</p>
          </div>
        </Popover>
      )}

      {open === "draw" && onDraw && (
        <Popover title="Draw a study area" onClose={() => setOpen(null)} wide>
          <div className="p-2">
            {(
              [
                ["circle", Circle, "Circle", "Click the centre, then click again to set the radius"],
                ["rectangle", RectangleHorizontal, "Rectangle", "Click the four corners"],
                ["polygon", Hexagon, "Polygon", "Click each corner; double-click or Enter to finish"],
              ] as [DrawMode, LucideIcon, string, string][]
            ).map(([k, Icon, l, hint]) => (
              <button
                key={k}
                type="button"
                onClick={() => {
                  onDraw(k);
                  setOpen(null);
                }}
                className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-start hover:bg-brand-50 dark:hover:bg-white/10"
              >
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-violet-600/10 text-violet-700 dark:text-violet-300">
                  <Icon className="h-4 w-4" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-semibold">{l}</span>
                  <span className="block text-[11px] text-ink-mute">{hint}</span>
                </span>
              </button>
            ))}
            <p className="px-3 pt-1 text-[10px] text-ink-mute">
              The portal then prepares a real-estate case study of the area: amenities, people, market, master plan, mega projects, outlook.
            </p>
          </div>
        </Popover>
      )}

      {open === "base" && (
        <Popover title="Base map" onClose={() => setOpen(null)}>
          <div className="p-2">
            {(Object.keys(BASE_MAPS) as BaseMapKey[]).map((k) => (
              <button
                key={k}
                type="button"
                onClick={() => {
                  onBase(k);
                  setOpen(null);
                }}
                className={cn("block w-full rounded-lg px-3 py-2 text-start text-sm font-medium", k === base ? "bg-brand-700 text-white" : "hover:bg-brand-50 dark:hover:bg-white/10")}
              >
                {BASE_MAPS[k].label}
              </button>
            ))}
          </div>
        </Popover>
      )}
      {open === "lang" && (
        <Popover title="Map labels" onClose={() => setOpen(null)}>
          <div className="p-2">
            {(
              [
                ["en", "English", "Province, city and place names in English"],
                ["ur", "اردو", "نام اردو میں"],
                ["both", "English + اردو", "Both, one under the other"],
              ] as [MapLang, string, string][]
            ).map(([k, l, hint]) => (
              <button
                key={k}
                type="button"
                onClick={() => {
                  onLang(k);
                  setOpen(null);
                }}
                className={cn("flex w-full items-center gap-2 rounded-lg px-3 py-2 text-start", k === lang ? "bg-brand-700 text-white" : "hover:bg-brand-50 dark:hover:bg-white/10")}
              >
                <span className="min-w-0 flex-1">
                  <span className={cn("block text-sm font-semibold", k === "ur" && "map-ur")}>{l}</span>
                  <span className={cn("block text-[11px]", k === lang ? "text-white/75" : "text-ink-mute")}>{hint}</span>
                </span>
                {k === lang && <Check className="h-4 w-4" />}
              </button>
            ))}
            <p className="px-3 pt-1 text-[10px] text-ink-mute">Street names on the base map come from the map provider.</p>
          </div>
        </Popover>
      )}
      {open === "layers" && (
        <Popover title={`Layers · ${activeCount} on`} onClose={() => setOpen(null)} wide>
          <div className="flex items-center gap-2 border-b border-black/5 px-3 py-2 dark:border-white/10">
            <div className="flex flex-1 items-center gap-2 rounded-lg bg-black/5 px-2.5 dark:bg-white/10">
              <Search className="h-3.5 w-3.5 text-ink-mute" />
              <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Find a layer…" className="h-8 w-full bg-transparent text-xs outline-none placeholder:text-ink-mute" />
            </div>
            <button type="button" onClick={() => setAll(true)} className="rounded-md px-1.5 py-1 text-[11px] font-semibold text-brand-700 hover:bg-brand-50 dark:text-brand-300 dark:hover:bg-white/10">
              All on
            </button>
            <button type="button" onClick={() => setAll(false)} className="rounded-md px-1.5 py-1 text-[11px] font-semibold text-ink-mute hover:bg-black/5 dark:hover:bg-white/10">
              All off
            </button>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {groups.map((g) => (
              <Section key={g.key} group={g} filter={filter} collapsed={!!collapsed[g.key]} onToggleCollapsed={() => toggleSection(g.key)} />
            ))}
          </div>
        </Popover>
      )}
    </div>
  );
}

const ADD_OPTIONS: [EditMode, LucideIcon, string, string, keyof EditRights][] = [
  ["add-property", MapPin, "Property listing", "Click where it is, then fill in the details", "property"],
  ["add-project", Building2, "Big project", "A mall, tower or mixed-use project (pin)", "project"],
  ["add-mega-point", Milestone, "Mega project · point", "An interchange, a tower, a zone centre", "mega"],
  ["add-mega-line", Spline, "Mega project · line", "A road, rail or transit line — click each bend", "mega"],
  ["add-mega-polygon", Square, "Mega project · area", "A new sector, zone or district — click its corners", "mega"],
];

/**
 * Admin map editing, as a horizontal bar (placed by the map page at the bottom left, beside the
 * explorer panel): Edit selects a feature to change; Add places a new one (menu opens upwards).
 */
export function EditBar({ edit, className }: { edit: { rights: EditRights; mode: EditMode; onMode: (m: EditMode) => void }; className?: string }) {
  const [menu, setMenu] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!menu) return;
    const close = (e: PointerEvent) => !ref.current?.contains(e.target as Node) && setMenu(false);
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [menu]);
  if (!edit.rights.property && !edit.rights.project && !edit.rights.mega) return null;
  const adding = !!edit.mode && edit.mode !== "select" && edit.mode !== "locate";
  const item = (active: boolean) =>
    cn("flex h-10 items-center gap-1.5 px-3 text-xs font-bold transition first:rounded-s-xl last:rounded-e-xl", active ? "bg-brand-700 text-white" : "text-brand-800 hover:bg-brand-50 dark:text-white dark:hover:bg-white/10");
  return (
    <div ref={ref} className={cn("absolute z-[450] flex flex-col items-start gap-1", className)}>
      <span className="rounded-full bg-white/90 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-ink-mute shadow-sm dark:bg-brand-950/90">Edit Listing</span>
      <div className="flex divide-x divide-black/5 rounded-xl bg-white shadow-soft ring-1 ring-black/5 dark:divide-white/10 dark:bg-brand-950">
        <button
          type="button"
          className={item(edit.mode === "select")}
          aria-pressed={edit.mode === "select"}
          title={edit.mode === "select" ? "Stop editing" : "Edit: click a listing, project or mega project to change it (saved to the database)"}
          onClick={() => {
            setMenu(false);
            edit.onMode(edit.mode === "select" ? null : "select");
          }}
        >
          <PencilLine className="h-4 w-4" /> Edit
        </button>
        <button
          type="button"
          className={item(menu || adding)}
          aria-expanded={menu}
          title={adding ? "Stop adding" : "Add a listing, a big project or a mega project on the map"}
          onClick={() => (adding ? edit.onMode(null) : setMenu((m) => !m))}
        >
          <Plus className="h-4 w-4" /> {adding ? "Adding…" : "Add"}
        </button>
        <button
          type="button"
          className={item(edit.mode === "locate")}
          aria-pressed={edit.mode === "locate"}
          title={edit.mode === "locate" ? "Close Locate" : "Locate: find records with a missing or wrong location and set it — map, coordinates, place search, GPS or society centre"}
          onClick={() => {
            setMenu(false);
            edit.onMode(edit.mode === "locate" ? null : "locate");
          }}
        >
          <LocateFixed className="h-4 w-4" /> Locate
        </button>
      </div>
      {menu && (
        <div className="absolute bottom-full start-0 mb-2 w-80 max-w-[calc(100vw-2rem)] overflow-hidden rounded-2xl bg-white p-2 shadow-2xl ring-1 ring-black/5 dark:bg-brand-950">
          {ADD_OPTIONS.filter((o) => edit.rights[o[4]]).map(([m, Icon, label, hint]) => (
            <button
              key={m}
              type="button"
              onClick={() => {
                edit.onMode(m);
                setMenu(false);
              }}
              className="flex w-full items-start gap-3 rounded-xl px-3 py-2.5 text-start transition hover:bg-brand-50 dark:hover:bg-white/10"
            >
              <Icon className="mt-0.5 h-4 w-4 shrink-0 text-gold-600" />
              <span>
                <span className="block text-sm font-semibold">{label}</span>
                <span className="block text-xs text-ink-mute">{hint}</span>
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
