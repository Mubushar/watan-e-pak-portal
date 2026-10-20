"""
Read a map view for the assistant: everything inside the bounds the user is looking at, from every
layer that is switched on — so "how many parks are here?", "what is this area?", "which roads?",
"which plans / layers are on?" get real numbers instead of guesses.

Sources, per view:
  • master plans in view — what the plan's own text says (parks, mosques, schools, blocks, roads …)
    and, read from the plan image's colours, its green areas (parks / open space). Image-only plans
    (no PDF text, e.g. most Bahria / society sheets) are read from colour alone.
  • OpenStreetMap places (schools, mosques, parks, hospitals, malls …), roads and the population estimate
  • portal listings, housing societies, mega projects
  • any other GIS layer switched on (uploaded / drawn layers): its features in view
"""

from __future__ import annotations

import math
import re
import sys
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import geo
import gis
import masterplan

MAX_SPAN_KM = 40.0        # beyond this only totals are given
IMAGE_MAX_SPAN_KM = 8.0   # plan images are read for views up to this size
IMAGE_MAX_PX = 1024       # mosaic size cap (per side) when reading a plan image
EXAMPLES = 6
_DEBUG: Optional[list] = None


def _core() -> Any:
    return sys.modules.get("server") or sys.modules.get("__main__")


def _in(b: Tuple[float, float, float, float], lat: Optional[float], lon: Optional[float]) -> bool:
    return lat is not None and lon is not None and b[0] <= lat <= b[2] and b[1] <= lon <= b[3]


def _km(b: Tuple[float, float, float, float]) -> Tuple[float, float]:
    lat = (b[0] + b[2]) / 2
    return (b[3] - b[1]) * 111.32 * math.cos(math.radians(lat)), (b[2] - b[0]) * 110.57


def _coords(g: Any) -> Iterable[Tuple[float, float]]:
    """Every [lon, lat] position in a GeoJSON geometry, as (lat, lon)."""
    if not isinstance(g, dict):
        return
    t, c = g.get("type"), g.get("coordinates")
    if t == "GeometryCollection":
        for sub in g.get("geometries") or []:
            yield from _coords(sub)
        return
    stack = [c]
    while stack:
        x = stack.pop()
        if isinstance(x, (list, tuple)) and len(x) >= 2 and all(isinstance(v, (int, float)) for v in x[:2]):
            yield float(x[1]), float(x[0])
        elif isinstance(x, (list, tuple)):
            stack.extend(x)


# ------------------------------------------------------------------ plan images

def _tile_xy(lat: float, lon: float, z: int) -> Tuple[float, float]:
    n = 2 ** z
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n
    return x, y


def _green_areas(key: str, b: Tuple[float, float, float, float], zoom: int) -> Optional[Dict[str, Any]]:
    """Green areas (parks / open space) drawn on a plan, read from its map tiles inside the view."""
    from PIL import Image, ImageChops, ImageFilter

    meta = masterplan.store().meta.get(key) or {}
    zr = meta.get("zoom") or [12, 17]
    tiles_dir = Path(masterplan.DIR) / key / "tiles"
    if not tiles_dir.exists():
        return None
    z = max(zr[0], min(zr[1], max(zoom, 14)))
    while True:
        x0, y0 = _tile_xy(b[2], b[1], z)
        x1, y1 = _tile_xy(b[0], b[3], z)
        if ((x1 - x0) * 256 <= IMAGE_MAX_PX and (y1 - y0) * 256 <= IMAGE_MAX_PX) or z <= zr[0]:
            break
        z -= 1
    tx0, ty0, tx1, ty1 = int(x0), int(y0), int(x1), int(y1)
    W, H = (tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256
    mosaic = Image.new("RGBA", (W, H))
    found = False
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            p = tiles_dir / str(z) / str(tx) / f"{ty}.png"
            if p.exists():
                mosaic.paste(Image.open(p).convert("RGBA"), ((tx - tx0) * 256, (ty - ty0) * 256))
                found = True
    if not found:
        return {"green_areas": 0, "note": "the plan does not reach into this view"}
    crop = (int((x0 - tx0) * 256), int((y0 - ty0) * 256), int((x1 - tx0) * 256) + 1, int((y1 - ty0) * 256) + 1)
    img = mosaic.crop(crop)
    alpha = img.getchannel("A").point(lambda v: 255 if v > 128 else 0)
    h, s, v = img.convert("RGB").convert("HSV").split()
    # Park green on these master plans is a fully saturated yellow-green to green (hue ~65–150°,
    # saturation ≥ 75 %). Pale lime residential plots (saturation ~50 %) and grey roads fall outside it.
    green = ImageChops.multiply(h.point(lambda x: 255 if 45 <= x <= 108 else 0), s.point(lambda x: 255 if x >= 190 else 0))
    green = ImageChops.multiply(green, v.point(lambda x: 255 if x >= 70 else 0))
    green = ImageChops.multiply(green, alpha)
    lat_c = (b[0] + b[2]) / 2
    mpp = 156543.03392 * math.cos(math.radians(lat_c)) / (2 ** z)
    # Opening removes green lines up to ~8 m wide (road verges / boundary lines joining the parks).
    k = max(3, min(7, int(round(8 / mpp)) | 1))
    green = green.filter(ImageFilter.MinFilter(k)).filter(ImageFilter.MaxFilter(k))
    w, hgt = green.size
    data = bytearray(green.tobytes())
    min_px = max(4, int(150 / (mpp * mpp)))  # ignore blobs under ~150 m²
    blobs: List[Tuple[int, float, float, float, float]] = []  # pixels, centre x, y, width m, height m
    for start in range(len(data)):
        if data[start] != 255:
            continue
        data[start] = 1
        q = deque([start])
        n = sx = sy = 0
        x_lo = y_lo = 10 ** 9
        x_hi = y_hi = -1
        while q:
            i = q.popleft()
            n += 1
            y, x = divmod(i, w)
            sx += x
            sy += y
            x_lo, x_hi, y_lo, y_hi = min(x_lo, x), max(x_hi, x), min(y_lo, y), max(y_hi, y)
            for j in (i - 1 if x else -1, i + 1 if x < w - 1 else -1, i - w, i + w):
                if 0 <= j < len(data) and data[j] == 255:
                    data[j] = 1
                    q.append(j)
        if n < min_px:
            continue
        bw, bh = (x_hi - x_lo + 1) * mpp, (y_hi - y_lo + 1) * mpp
        if _DEBUG is not None:
            _DEBUG.append((round(n * mpp * mpp), round(bw), round(bh)))
        blobs.append((n, sx / n * mpp, sy / n * mpp, bw, bh))
    px_area = mpp * mpp
    # Dashed lines (a scheme boundary drawn as thick green dashes) break into chains of near-identical
    # small pieces one or two lengths apart; parks of one size sit much further apart. Drop such chains.
    dash = set()
    small = [i for i, bl in enumerate(blobs) if bl[0] * px_area < 1500]
    link: Dict[int, List[int]] = defaultdict(list)
    for a in small:
        for c in small:
            if a < c and abs(blobs[a][0] - blobs[c][0]) <= 0.4 * max(blobs[a][0], blobs[c][0]):
                gap = math.hypot(blobs[a][1] - blobs[c][1], blobs[a][2] - blobs[c][2])
                if gap <= 2.5 * math.sqrt(max(blobs[a][0], blobs[c][0]) * px_area):
                    link[a].append(c)
                    link[c].append(a)
    seen: set = set()
    for a in small:
        if a in seen:
            continue
        group, stack = [], [a]
        seen.add(a)
        while stack:
            i = stack.pop()
            group.append(i)
            for j in link[i]:
                if j not in seen:
                    seen.add(j)
                    stack.append(j)
        if len(group) >= 4:
            dash.update(group)
    parks: List[int] = []
    belts: List[int] = []
    for i, (n, _, _, bw, bh) in enumerate(blobs):
        if i in dash:
            continue
        fill = n * px_area / max(bw * bh, 1e-9)
        # A park is a compact patch; a long thin (or sparse, L-shaped) one is a green belt / verge.
        if max(bw, bh) / max(min(bw, bh), 1e-9) > 4 or (fill < 0.35 and min(bw, bh) < 40):
            belts.append(n)
        else:
            parks.append(n)
    covered = sum(1 for a in alpha.tobytes() if a) * px_area
    return {
        "parks_green_patches": len(parks),
        "parks_area_m2": round(sum(parks) * px_area),
        "largest_park_m2": round(max(parks) * px_area) if parks else 0,
        "green_belts_strips": len(belts),
        "green_belts_area_m2": round(sum(belts) * px_area),
        "plan_area_in_view_m2": round(covered),
        "read_at": f"zoom {z} (~{mpp:.1f} m per pixel)",
    }


# ------------------------------------------------------------------ main

def read(south: float, west: float, north: float, east: float, zoom: int = 15,
         plans: Optional[Sequence[str]] = None, gis_ids: Optional[Sequence[str]] = None,
         overlays: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """Everything inside the view. ``plans`` / ``gis_ids`` / ``overlays`` say which layers the user has
    switched on (None = all published)."""
    import megaprojects

    core = _core()
    if not (-90 <= south < north <= 90 and -180 <= west < east <= 180):
        return {"error": "bounds must be south < north and west < east"}
    b = (south, west, north, east)
    wkm, hkm = _km(b)
    span = max(wkm, hkm)
    big = span > MAX_SPAN_KM
    lat_c, lon_c = (south + north) / 2, (west + east) / 2
    ring = [[south, west], [south, east], [north, east], [north, west]]
    shape = geo.Shape([ring])
    on = set(overlays) if overlays is not None else None
    notes: List[str] = []

    out: Dict[str, Any] = {
        "view": {"center": [round(lat_c, 6), round(lon_c, 6)], "zoom": zoom,
                 "bounds": {"south": south, "west": west, "north": north, "east": east},
                 "size_km": [round(wkm, 2), round(hkm, 2)], "area_km2": round(wkm * hkm, 3)},
    }
    try:
        city = min(core.cities_db, key=lambda c: geo.haversine_km(lat_c, lon_c, c.latitude, c.longitude)
                   if c.latitude is not None else 1e9)
        out["view"]["nearest_city"] = {"name": city.name, "distance_km": round(geo.haversine_km(lat_c, lon_c, city.latitude, city.longitude), 1)}
    except Exception:
        pass

    # ---- master plans in view
    store = masterplan.store()
    in_view_plans = [m for m in store.meta.values()
                     if m["bounds"][0] <= north and m["bounds"][2] >= south and m["bounds"][1] <= east and m["bounds"][3] >= west]
    shown = set(plans) if plans is not None else None
    plan_rows = []
    for m in in_view_plans:
        row: Dict[str, Any] = {"plan": m["name"], "key": m["key"], "group": m.get("group", "dha"),
                               "society": m.get("scheme"), "switched_on": shown is None or m["key"] in shown,
                               "credit": masterplan.credit(m)}
        labels = store.labels.get(m["key"]) or []
        if labels:
            here = [r for r in labels if _in(b, r[2], r[3])]
            counts = Counter(masterplan.CATEGORY_LABELS.get(r[1], r[1]) for r in here
                             if r[1] not in ("dimension", "infrastructure", "label"))
            row["from_plan_text"] = dict(counts.most_common())
            names: Dict[str, List[str]] = defaultdict(list)
            for r in here:
                if r[1] in ("sector", "park", "mosque", "education", "health", "commercial", "community", "road", "water", "graveyard"):
                    lab = masterplan.CATEGORY_LABELS.get(r[1], r[1])
                    if r[0] not in names[lab] and len(names[lab]) < EXAMPLES:
                        names[lab].append(r[0])
            row["names_on_plan"] = dict(names)
        else:
            row["from_plan_text"] = None
            row["note"] = "This plan is an image (no text layer): its contents are read from the drawing's colours."
        if not big and span <= IMAGE_MAX_SPAN_KM:
            try:
                g = _green_areas(m["key"], b, zoom)
                if g:
                    row["from_plan_image"] = g
            except Exception as e:  # never fail the whole read for one image
                row["from_plan_image"] = {"error": str(e)[:120]}
        plan_rows.append(row)
    out["master_plans"] = plan_rows
    if any(r.get("from_plan_image") for r in plan_rows):
        notes.append("Parks are counted from the master plan drawing's colours: compact green patches = parks / open spaces, long thin ones = green belts / verges "
                     "(reported apart). A park cut by the edge of the view counts once; patches under ~150 m² are ignored. Approximate — say so.")
    if span > IMAGE_MAX_SPAN_KM and plan_rows:
        notes.append(f"The view is {span:.0f} km across: zoom in (under {IMAGE_MAX_SPAN_KM:.0f} km) to count green areas on the plan drawings.")

    # ---- OpenStreetMap places, population
    if geo.available():
        places = geo.places_in(shape)
        by_kind = Counter(p.get("kind") or p.get("category") for p in places)
        examples: Dict[str, List[str]] = defaultdict(list)
        for p in places:
            k = p.get("kind") or p.get("category")
            if p.get("name") and len(examples[k]) < EXAMPLES and p["name"] not in examples[k]:
                examples[k].append(p["name"])
        out["places_openstreetmap"] = {"total": len(places), "by_kind": dict(by_kind.most_common(30)),
                                       "names": {k: v for k, v in examples.items() if k in dict(by_kind.most_common(12))}}
        try:
            out["population_estimate"] = geo.population_in(shape)
        except Exception:
            pass

    # ---- roads
    try:
        import roads
        if roads.available() and span <= MAX_SPAN_KM:
            named: Dict[str, str] = {}
            for r in roads._load()["roads"]:
                rb = r["b"]
                if rb[0] <= north and rb[2] >= south and rb[1] <= east and rb[3] >= west:
                    label = r.get("n") or r.get("r")
                    if label and label not in named:
                        named[label] = r["c"]
            order = ["motorway", "trunk", "primary", "secondary", "tertiary"]
            major = sorted((n for n, c in named.items() if c in order), key=lambda n: order.index(named[n]))
            out["roads"] = {"named_roads": len(named), "major": major[:15],
                            "other_examples": [n for n, c in named.items() if c not in order][:10]}
    except Exception:
        pass

    # ---- portal data
    props = [p for p in core.properties_db if _in(b, p.latitude, p.longitude) and getattr(p, "status", "active") != "deleted"]
    if props:
        prices = [p.price for p in props if p.price]
        out["listings"] = {"count": len(props), "switched_on": on is None or "listings" in on,
                           "by_category": dict(Counter(p.category for p in props).most_common()),
                           "price_range": [min(prices), max(prices)] if prices else None,
                           "examples": [p.title for p in props[:EXAMPLES]]}
    schemes = [s for s in core.housing_schemes_db if _in(b, s.latitude, s.longitude)]
    if schemes:
        out["housing_societies"] = [s.name for s in schemes[:20]]
    megas = []
    for mp in megaprojects.all_projects():
        geom = mp.get("geometry") or {}
        c = geom.get("center")
        pts = [*(geom.get("path") or []), *(geom.get("ring") or [])]  # [lat, lon] pairs
        # lines are drawn between sparse points: sample along each leg so one crossing the view counts
        pts += [(p1[0] + (p2[0] - p1[0]) * t / 40, p1[1] + (p2[1] - p1[1]) * t / 40)
                for p1, p2 in zip(pts, pts[1:]) for t in range(1, 40)]
        if (c and _in(b, c[0], c[1])) or any(_in(b, pt[0], pt[1]) for pt in pts):
            megas.append(f"{mp['name']} ({mp.get('type')})")
    if megas:
        out["mega_projects"] = megas[:20]

    # ---- other GIS layers (uploaded / drawn), whichever are switched on
    wanted = set(gis_ids) if gis_ids is not None else None
    plan_names = {m["name"].lower() for m in store.meta.values()}
    layer_rows = []
    for layer in gis.GIS_LAYERS:
        if not layer.published or (layer.geojson_ref or "").startswith(("builtin:", "masterplan")):
            continue
        if layer.layer_type in ("master_plan", "annotation") or (wanted is not None and layer.id not in wanted):
            continue
        if re.sub(r" — (boundary|master plan|plan labels: .*)$", "", layer.name).lower() in plan_names:
            continue  # a master plan's own outline
        feats = (layer.geojson or {}).get("features") or []
        n = sum(1 for f in feats if any(_in(b, la, lo) for la, lo in _coords((f or {}).get("geometry"))))
        if n:
            layer_rows.append({"layer": layer.name, "type": layer.layer_type, "features_in_view": n})
    if layer_rows:
        out["gis_layers"] = layer_rows

    if big:
        notes.append(f"The view is {span:.0f} km across — counts are totals; zoom in for detail.")
    out["notes"] = notes
    return out
