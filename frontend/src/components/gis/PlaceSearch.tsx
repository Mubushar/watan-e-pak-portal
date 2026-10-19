/**
 * Google-style place / address search field with type-ahead suggestions.
 *   GET /geo/suggest?q=…   cities, housing societies, listings, sectors / societies, places
 *   GET /geo/geocode?q=…   on Enter without a pick: local data, then OpenStreetMap (once)
 * Used by the map's search bar and the route finder's From / To fields.
 */
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Building2, Home, Landmark, Loader2, MapPin, Navigation, Search, X, type LucideIcon } from "lucide-react";
import { get } from "@/lib/api";
import { cn } from "@/lib/utils";

export interface PlaceHit {
  type: "city" | "scheme" | "listing" | "area" | "place" | "address" | "here" | "picked";
  label: string;
  sub?: string;
  lat: number;
  lon: number;
  zoom?: number;
  id?: string;
  bounds?: [number, number, number, number] | null;
}

const ICONS: Record<string, LucideIcon> = { city: Building2, scheme: Landmark, listing: Home, area: MapPin, place: MapPin, address: MapPin, here: Navigation, picked: MapPin };

export function PlaceSearch({
  value,
  onPick,
  placeholder = "Search places & addresses",
  icon,
  extra,
  autoFocus,
  className,
  inputClassName,
}: {
  /** The picked place's label shown in the field (controlled from outside, e.g. after "use my location"). */
  value?: string;
  onPick: (hit: PlaceHit) => void;
  placeholder?: string;
  icon?: ReactNode;
  /** Extra rows at the top of the dropdown (e.g. "Your location", "Pick on map"). */
  extra?: { label: string; icon: LucideIcon; onSelect: () => void }[];
  autoFocus?: boolean;
  className?: string;
  inputClassName?: string;
}) {
  const [text, setText] = useState(value ?? "");
  const [hits, setHits] = useState<PlaceHit[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const seq = useRef(0);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => setText(value ?? ""), [value]);

  // Debounced type-ahead.
  useEffect(() => {
    const q = text.trim();
    if (!open || q.length < 2 || q === value) {
      setHits([]);
      return;
    }
    const id = ++seq.current;
    const t = setTimeout(async () => {
      try {
        const r = await get<{ suggestions: PlaceHit[] }>("/geo/suggest", { q, limit: 8 }, { noFallback: true });
        if (id === seq.current) {
          setHits(r.suggestions);
          setActive(r.suggestions.length ? 0 : -1);
          setError(null);
        }
      } catch {
        if (id === seq.current) setHits([]);
      }
    }, 220);
    return () => clearTimeout(t);
  }, [text, open, value]);

  useEffect(() => {
    if (!open) return;
    const close = (e: PointerEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);

  const pick = (h: PlaceHit) => {
    setText(h.label);
    setOpen(false);
    setHits([]);
    onPick(h);
  };

  const submit = async () => {
    if (active >= 0 && hits[active]) return pick(hits[active]!);
    const q = text.trim();
    if (q.length < 2) return;
    setBusy(true);
    setError(null);
    try {
      const r = await get<PlaceHit>("/geo/geocode", { q }, { noFallback: true });
      pick({ ...r, type: "address", zoom: r.bounds ? undefined : 16 });
    } catch (e) {
      setError((e as Error).message || `Couldn't find "${q}"`);
      setOpen(true);
    } finally {
      setBusy(false);
    }
  };

  const rows = [...(extra ?? []).map((x) => ({ kind: "extra" as const, ...x })), ...hits.map((h) => ({ kind: "hit" as const, h }))];

  return (
    <div ref={box} className={cn("relative", className)}>
      <div className={cn("flex items-center gap-2 rounded-xl bg-white px-3 ring-1 ring-black/10 focus-within:ring-2 focus-within:ring-brand-500 dark:bg-brand-950 dark:ring-white/15", inputClassName)}>
        {icon ?? <Search className="h-4 w-4 shrink-0 text-ink-mute" />}
        <input
          value={text}
          autoFocus={autoFocus}
          onChange={(e) => {
            setText(e.target.value);
            setOpen(true);
            setError(null);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setActive((a) => Math.min(hits.length - 1, a + 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setActive((a) => Math.max(-1, a - 1));
            } else if (e.key === "Enter") {
              e.preventDefault();
              void submit();
            } else if (e.key === "Escape") setOpen(false);
          }}
          placeholder={placeholder}
          className="h-10 min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-ink-mute"
          role="combobox"
          aria-expanded={open && rows.length > 0}
          aria-autocomplete="list"
        />
        {busy ? (
          <Loader2 className="h-4 w-4 animate-spin text-ink-mute" />
        ) : (
          text && (
            <button
              type="button"
              onClick={() => {
                setText("");
                setHits([]);
                setOpen(true);
              }}
              className="text-ink-mute hover:text-ink"
              aria-label="Clear"
            >
              <X className="h-4 w-4" />
            </button>
          )
        )}
      </div>
      {open && (rows.length > 0 || error) && (
        <div className="absolute inset-x-0 top-full z-[600] mt-1 overflow-hidden rounded-xl bg-white shadow-2xl ring-1 ring-black/5 dark:bg-brand-950" role="listbox">
          {rows.map((r, i) =>
            r.kind === "extra" ? (
              <button
                key={`x${i}`}
                type="button"
                onClick={() => {
                  setOpen(false);
                  r.onSelect();
                }}
                className="flex w-full items-center gap-3 px-3 py-2 text-start text-sm font-semibold text-brand-700 hover:bg-brand-50 dark:text-brand-300 dark:hover:bg-white/5"
              >
                <r.icon className="h-4 w-4" /> {r.label}
              </button>
            ) : (
              <HitRow key={`${r.h.type}-${r.h.label}-${i}`} h={r.h} active={i - (extra?.length ?? 0) === active} onPick={pick} />
            ),
          )}
          {error && <p className="px-3 py-2 text-xs text-red-600">{error}</p>}
          {!error && hits.length > 0 && <p className="border-t border-black/5 px-3 py-1.5 text-[10px] text-ink-mute dark:border-white/10">Press Enter to search any address</p>}
        </div>
      )}
    </div>
  );
}

function HitRow({ h, active, onPick }: { h: PlaceHit; active: boolean; onPick: (h: PlaceHit) => void }) {
  const Icon = ICONS[h.type] ?? MapPin;
  return (
    <button
      type="button"
      role="option"
      aria-selected={active}
      onMouseDown={(e) => e.preventDefault()}
      onClick={() => onPick(h)}
      className={cn("flex w-full items-center gap-3 px-3 py-2 text-start transition", active ? "bg-brand-50 dark:bg-white/10" : "hover:bg-brand-50/70 dark:hover:bg-white/5")}
    >
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-black/5 text-ink-soft dark:bg-white/10 dark:text-slate-300">
        <Icon className="h-4 w-4" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-semibold">{h.label}</span>
        {h.sub && <span className="block truncate text-[11px] text-ink-mute">{h.sub}</span>}
      </span>
    </button>
  );
}
