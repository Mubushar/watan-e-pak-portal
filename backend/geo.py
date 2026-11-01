"""
Places, areas and population for the assistant ("which malls are in Bahria Phase 8?",
"how many high schools are in DHA 2 Islamabad?", "a room near Rawalpindi Medical
University", "how developed is G-13 and how many people live there?").

Data comes from ``geodata/*.json.gz`` (built by ``geodata/build_geodata.py``):

* places      named schools, colleges, universities, hospitals, mosques, malls, parks, … (OpenStreetMap)
* areas       neighbourhoods, sectors, phases and housing societies with outlines (OpenStreetMap / Nominatim)
* population  people per ~0.74 km² hexagon (Kontur Population 2023)

Names the offline data doesn't know can be looked up on OpenStreetMap's Nominatim
(``GEO_ONLINE_LOOKUP=1``, the default; cached, at most one request per second).

Data © OpenStreetMap contributors (ODbL); population © Kontur (CC BY 4.0).
"""

from __future__ import annotations

import gzip
import io
import json
import math
import os
import re
import threading
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import httpx

import storage
import envfile  # noqa: F401  (loads backend/.env)

DATA_DIR = Path(__file__).resolve().parent / "geodata"
ONLINE_LOOKUP = os.getenv("GEO_ONLINE_LOOKUP", "1").strip().lower() in ("1", "true", "yes", "on")
ATTRIBUTION = "Places and areas © OpenStreetMap contributors; population © Kontur Population 2023."
# Map tiles for the apps' map cards. OpenStreetMap's own tiles are fine for light use;
# for a busy launch use a tile provider (MapTiler, Stadia, Thunderforest …) and its URL.
TILE_URL = os.getenv("MAP_TILE_URL", "https://tile.openstreetmap.org/{z}/{x}/{y}.png")
TILE_ATTRIBUTION = os.getenv("MAP_TILE_ATTRIBUTION", "© OpenStreetMap contributors")
MAP_KINDS = ["school", "mosque", "park", "mall", "hospital"]

CELL = 0.01  # spatial index cell, degrees (~1.1 km)
HEX_KM2 = 0.737

# Plain names for each category, used in answers.
CATEGORY_LABELS = {
    "education": "School / college", "worship": "Mosque", "health": "Hospital / clinic",
    "shopping": "Mall / market", "park": "Park", "bank": "Bank", "restaurant": "Restaurant",
    "transport": "Public transport", "fuel": "Fuel station", "government": "Government office",
}
KIND_LABELS = {
    "school": "School", "kindergarten": "Kindergarten", "college": "College", "university": "University",
    "hospital": "Hospital", "clinic": "Clinic", "pharmacy": "Pharmacy", "mosque": "Mosque", "mall": "Mall",
    "supermarket": "Supermarket", "market": "Market", "park": "Park", "sports": "Sports ground",
    "bank": "Bank", "restaurant": "Restaurant", "cafe": "Café", "fast_food": "Fast food", "station": "Station",
    "fuel": "Fuel station", "police": "Police", "townhall": "Government office", "courthouse": "Court",
    "post_office": "Post office",
}

# What people ask for -> (category, kinds or None for any, words the name must contain)
KINDS: Dict[str, Tuple[str, Optional[Tuple[str, ...]], Tuple[str, ...]]] = {
    "school": ("education", ("school",), ()),
    "high school": ("education", ("school",), ("high",)),
    "primary school": ("education", ("school",), ("primary",)),
    "college": ("education", ("college",), ()),
    "university": ("education", ("university", "college"), ("universit",)),
    "medical college": ("education", ("college", "university"), ("medical",)),
    "kindergarten": ("education", ("kindergarten",), ()),
    "education": ("education", None, ()),
    "hospital": ("health", ("hospital",), ()),
    "clinic": ("health", ("clinic",), ()),
    "pharmacy": ("health", ("pharmacy",), ()),
    "health": ("health", None, ()),
    "mosque": ("worship", ("mosque",), ()),
    "masjid": ("worship", ("mosque",), ()),
    "mall": ("shopping", ("mall",), ()),
    "supermarket": ("shopping", ("supermarket",), ()),
    "market": ("shopping", ("market", "mall", "supermarket"), ()),
    "shopping": ("shopping", None, ()),
    "park": ("park", ("park",), ()),
    "sports": ("park", ("sports",), ()),
    "bank": ("bank", None, ()),
    "restaurant": ("restaurant", None, ()),
    "cafe": ("restaurant", ("cafe",), ()),
    "transport": ("transport", None, ()),
    "station": ("transport", None, ()),
    "fuel": ("fuel", None, ()),
    "petrol": ("fuel", None, ()),
    "police": ("government", ("police",), ()),
    "government": ("government", None, ()),
}

# Common names people use for places mapped under another name.
ALIASES = {
    "rawalpindi medical university": "rawalpindi medical college",
    "rmu": "rawalpindi medical college",
    "nust": "national university of sciences and technology",
    "pims": "pakistan institute of medical sciences",
    "qau": "quaid-i-azam university",
    "lums": "lahore university of management sciences",
    "aku": "aga khan university hospital",
    "cmh": "combined military hospital",
}
CITY_WORDS = {
    "islamabad": "islamabad_rawalpindi", "isb": "islamabad_rawalpindi", "rawalpindi": "islamabad_rawalpindi",
    "pindi": "islamabad_rawalpindi", "lahore": "lahore", "lhr": "lahore", "karachi": "karachi", "khi": "karachi",
}
FACILITY_WORDS = {
    "university", "college", "school", "academy", "institute", "hospital", "clinic", "medical", "mall", "plaza",
    "market", "bazaar", "mosque", "masjid", "park", "station", "stadium", "airport", "chowk", "centre", "center",
    "rmu", "nust", "pims", "qau", "lums", "aku", "cmh",
}
STOP = {"the", "in", "of", "near", "at", "area", "society", "housing", "scheme", "town", "pakistan", "and", "a", "ke", "ki", "ka", "mein"}
ROMAN = {"i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "vii": "7", "viii": "8", "ix": "9", "x": "10"}


# ------------------------------------------------------------------ text

def normalize(text: str) -> str:
    t = " " + (text or "").lower() + " "
    t = t.replace("defence housing authority", "dha").replace("defense housing authority", "dha")
    t = re.sub(r"bahria\s+town", "bahria", t)
    t = re.sub(r"[,.;:()/\\'\"]", " ", t)
    t = re.sub(r"\bph(?:ase)?[\s-]*(\d+|[ivx]+)\b", lambda m: f" phase {ROMAN.get(m.group(1), m.group(1))} ", t)
    t = re.sub(r"\b(dha|bahria)\s+(\d+)\b", r"\1 phase \2", t)                 # "dha 2" -> "dha phase 2"
    t = re.sub(r"(?<![\w-])([a-i])\s*-?\s*(\d{1,2})(?![\w-])", r"\1-\2", t)     # "g 13", "g13" -> "g-13"
    return " ".join(t.split())


def tokens(text: str) -> List[str]:
    return [w for w in normalize(text).split() if w not in STOP]


def _region_hint(words: Sequence[str]) -> Tuple[Optional[str], List[str]]:
    region = next((CITY_WORDS[w] for w in words if w in CITY_WORDS), None)
    return region, [w for w in words if w not in CITY_WORDS]


def _score(query: Sequence[str], name_tokens: Sequence[str], extra: Iterable[str] = ()) -> float:
    if not query:
        return 0.0
    have = set(name_tokens) | set(extra)
    nums = [w for w in query if any(ch.isdigit() for ch in w)]
    # "phase 8" must not match "phase 2"; an area with its own number must carry the asked one.
    own_nums = any(any(ch.isdigit() for ch in w) for w in name_tokens)
    if any(n not in (name_tokens if own_nums else have) for n in nums):
        return 0.0
    hit = sum(1 for w in query if w in have)
    if hit == 0:
        return 0.0
    # Prefer areas whose own name says it, without extra words ("Johar Town", not "Johar View").
    own = sum(1 for w in query if w in name_tokens)
    extra_words = len([w for w in name_tokens if w not in query])
    return hit / len(query) + 0.05 * own / len(query) - 0.05 * extra_words


# ------------------------------------------------------------------ geometry

def haversine_km(a: float, b: float, c: float, d: float) -> float:
    p1, p2 = math.radians(a), math.radians(c)
    dp, dl = p2 - p1, math.radians(d - b)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(h))


def point_in_ring(lat: float, lon: float, ring: Sequence[Sequence[float]]) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        yi, xi = ring[i]
        yj, xj = ring[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


class Shape:
    """An area to search in: outlines and/or circles (an area mapped only as a point
    becomes a circle of a typical size for its kind)."""

    def __init__(self, rings: Sequence[Sequence[Sequence[float]]] = (), center: Optional[Tuple[float, float]] = None,
                 radius_km: Optional[float] = None, circles: Sequence[Tuple[float, float, float]] = ()):
        self.rings = [r for r in rings if len(r) >= 3 and all(_finite(*p[:2]) for p in r)]
        self.circles = [c for c in circles if _finite(*c[:3]) and c[2] > 0]
        if center and radius_km and _finite(center[0], center[1], radius_km) and radius_km > 0:
            self.circles.append((center[0], center[1], min(float(radius_km), MAX_RADIUS_KM)))
        self.center = center or (self.circles[0][:2] if self.circles else None)
        self.radius_km = radius_km
        boxes = []
        for r in self.rings:
            boxes.append((min(p[0] for p in r), min(p[1] for p in r), max(p[0] for p in r), max(p[1] for p in r)))
        for lat, lon, rad in self.circles:
            dlat = rad / 111.0
            dlon = rad / (111.0 * max(0.2, math.cos(math.radians(lat))))
            boxes.append((lat - dlat, lon - dlon, lat + dlat, lon + dlon))
        self.box = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes),
                    max(b[3] for b in boxes)) if boxes else None

    def contains(self, lat: float, lon: float) -> bool:
        if not self.box or not (self.box[0] <= lat <= self.box[2] and self.box[1] <= lon <= self.box[3]):
            return False
        if any(point_in_ring(lat, lon, r) for r in self.rings):
            return True
        return any(haversine_km(c[0], c[1], lat, lon) <= c[2] for c in self.circles)

    @property
    def area_km2(self) -> float:
        return sum(_ring_area_km2(r) for r in self.rings) + sum(math.pi * c[2] ** 2 for c in self.circles)


def _ring_area_km2(ring: Sequence[Sequence[float]]) -> float:
    lat0 = math.radians(sum(p[0] for p in ring) / len(ring))
    xy = [(math.radians(p[1]) * math.cos(lat0) * 6371.0088, math.radians(p[0]) * 6371.0088) for p in ring]
    s = sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(xy, xy[1:] + xy[:1]))
    return abs(s) / 2.0


# ------------------------------------------------------------------ data

class _Data:
    def __init__(self) -> None:
        self.places: List[Dict[str, Any]] = []
        self.areas: List[Dict[str, Any]] = []
        self.cells: List[Tuple[float, float, int]] = []
        self.place_grid: Dict[Tuple[int, int], List[int]] = defaultdict(list)
        self.cell_grid: Dict[Tuple[int, int], List[int]] = defaultdict(list)
        self.regions: Dict[str, Dict[str, Any]] = {}
        self.built: Optional[str] = None


_data: Optional[_Data] = None
_load_lock = threading.Lock()


MAX_RADIUS_KM = 100.0  # the widest circle any search may draw


def _finite(*values: Any) -> bool:
    try:
        return all(math.isfinite(float(v)) for v in values)
    except (TypeError, ValueError):
        return False


def _key(lat: float, lon: float) -> Tuple[int, int]:
    return int(math.floor(lat / CELL)), int(math.floor(lon / CELL))


def _read(name: str) -> Optional[Dict[str, Any]]:
    path = DATA_DIR / name
    raw = storage.read_seed_asset(f"geodata/{name}", str(path))
    if not raw:
        return None
    with gzip.open(io.BytesIO(raw), "rt", encoding="utf-8") as f:
        return json.load(f)


def data() -> _Data:
    """The loaded geodata (loaded on first use)."""
    global _data
    if _data is not None:
        return _data
    with _load_lock:
        if _data is not None:
            return _data
        d = _Data()
        places, areas, pop = _read("places.json.gz"), _read("areas.json.gz"), _read("population.json.gz")
        if places:
            d.regions = places["meta"]["regions"]
            d.built = places["meta"].get("built")
            for region, rows in places["regions"].items():
                for name, name_ur, cat, kind, lat, lon in rows:
                    d.place_grid[_key(lat, lon)].append(len(d.places))
                    d.places.append({"name": name, "name_ur": name_ur, "category": cat, "kind": kind,
                                     "lat": lat, "lon": lon, "region": region, "tokens": tokens(name)})
        if areas:
            for region, rows in areas["regions"].items():
                for a in rows:
                    a["region"] = region
                    a["tokens"] = tokens(a["name"])
                    a["parent_tokens"] = [w for p in a.get("parents", []) for w in tokens(p)]
                    d.areas.append(a)
        if pop:
            for rows in pop["regions"].values():
                for lat, lon, n in rows:
                    d.cell_grid[_key(lat, lon)].append(len(d.cells))
                    d.cells.append((lat, lon, n))
        _data = d
        return d


def available() -> bool:
    return bool(data().places or data().areas)


def places_bbox(south: float, west: float, north: float, east: float, categories: Optional[Iterable[str]] = None,
                limit: int = 2000) -> Tuple[List[Dict[str, Any]], int]:
    """Places inside a lat/lon box (for a map's visible area), optionally only some categories.
    Returns (places, total matched); at most ``limit`` are returned."""
    d = data()
    cats = set(categories) if categories else None
    rows, total = [], 0
    for i in _scan(d.place_grid, (south, west, north, east)):
        p = d.places[i]
        if not (south <= p["lat"] <= north and west <= p["lon"] <= east) or (cats and p["category"] not in cats):
            continue
        total += 1
        if len(rows) < limit:
            rows.append({"name": p["name"], "name_ur": p.get("name_ur"), "category": p["category"], "kind": p["kind"],
                         "kind_label": KIND_LABELS.get(p["kind"], p["kind"].replace("_", " ").title()),
                         "lat": p["lat"], "lon": p["lon"]})
    return rows, total


def _prefix_score(query: Sequence[str], name: str, name_tokens: Sequence[str]) -> float:
    """Type-ahead match: every query word must start a word of the name (the last may be partial)."""
    if not query:
        return 0.0
    for w in query:
        if not any(t.startswith(w) for t in name_tokens):
            return 0.0
    norm = normalize(name)
    q = " ".join(query)
    return 3.0 if norm == q else 2.0 if norm.startswith(q) else 1.0


def suggest_local(text: str, limit: int = 8) -> List[Dict[str, Any]]:
    """Areas (sectors, societies, neighbourhoods) and places matching what is typed so far."""
    q = tokens(text)
    if not q or len(" ".join(q)) < 2:
        return []
    d = data()
    out: List[Tuple[float, Dict[str, Any]]] = []
    for a in d.areas:
        s = _prefix_score(q, a["name"], a["tokens"])
        if s:
            region = d.regions.get(a.get("region", ""), {}).get("label", "")
            parent = (a.get("parents") or [])[:1]
            out.append((s + 0.6 + min(0.3, (a.get("population") or 0) / 1_000_000),
                        {"type": "area", "label": a["name"], "sub": ", ".join([*parent, region] if region else parent),
                         "lat": a["center"][0], "lon": a["center"][1], "zoom": 15 if (a.get("area_km2") or 1) < 3 else 14}))
    for p in d.places:
        s = _prefix_score(q, p["name"], p["tokens"])
        if s:
            region = d.regions.get(p.get("region", ""), {}).get("label", "")
            kind = KIND_LABELS.get(p["kind"], p["kind"].replace("_", " ").title())
            # A shop or school named "Faisal" shouldn't outrank Faisal Town.
            out.append((s - 0.8, {"type": "place", "label": p["name"], "sub": f"{kind} · {region}" if region else kind,
                            "lat": p["lat"], "lon": p["lon"], "zoom": 17, "category": p["category"]}))
            if len(out) > 600:
                break
    out.sort(key=lambda x: -x[0])
    seen, rows = set(), []
    for _, r in out:
        k = (r["label"].lower(), round(r["lat"], 3), round(r["lon"], 3))
        if k in seen:
            continue
        seen.add(k)
        rows.append(r)
        if len(rows) >= limit:
            break
    return rows


def _scan(grid: Dict[Tuple[int, int], List[int]], box: Tuple[float, float, float, float]) -> Iterable[int]:
    if not _finite(*box):
        return
    i0, j0 = _key(box[0], box[1])
    i1, j1 = _key(box[2], box[3])
    if (i1 - i0 + 1) * (j1 - j0 + 1) > len(grid):  # a huge box: walk the occupied cells instead
        for (i, j), rows in grid.items():
            if i0 <= i <= i1 and j0 <= j <= j1:
                yield from rows
        return
    for i in range(i0, i1 + 1):
        for j in range(j0, j1 + 1):
            yield from grid.get((i, j), ())


def places_in(shape: Shape) -> List[Dict[str, Any]]:
    d = data()
    if not shape.box:
        return []
    return [d.places[i] for i in _scan(d.place_grid, shape.box) if shape.contains(d.places[i]["lat"], d.places[i]["lon"])]


def population_in(shape: Shape) -> int:
    """People living in an area (Kontur 2023 estimate)."""
    d = data()
    if not shape.box or not d.cells:
        return 0
    inside = [d.cells[i] for i in _scan(d.cell_grid, shape.box) if shape.contains(d.cells[i][0], d.cells[i][1])]
    if len(inside) >= 3:
        return int(sum(c[2] for c in inside))
    # A small area: local density × its size.
    c = shape.center or ((shape.box[0] + shape.box[2]) / 2, (shape.box[1] + shape.box[3]) / 2)
    near = [d.cells[i] for i in _scan(d.cell_grid, Shape(center=c, radius_km=0.8).box or shape.box)
            if haversine_km(c[0], c[1], d.cells[i][0], d.cells[i][1]) <= 0.8] or inside
    if not near:
        return 0
    return int(sum(x[2] for x in near) / (len(near) * HEX_KM2) * shape.area_km2)


def nearest_places(lat: float, lon: float, radius_km: float = 3.0, category: Optional[str] = None,
                   kinds: Optional[Sequence[str]] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Places around a point, closest first, with distance."""
    rows = []
    for p in places_in(Shape(center=(lat, lon), radius_km=radius_km)):
        if category and p["category"] != category:
            continue
        if kinds and p["kind"] not in kinds:
            continue
        rows.append((haversine_km(lat, lon, p["lat"], p["lon"]), p))
    rows.sort(key=lambda r: r[0])
    return [_place_view(p, dist) for dist, p in rows[:limit]]


def _place_view(p: Dict[str, Any], dist_km: Optional[float] = None) -> Dict[str, Any]:
    v = {"name": p["name"], "kind": KIND_LABELS.get(p["kind"], p["kind"].title()), "category": p["category"],
         "latitude": p["lat"], "longitude": p["lon"]}
    if p.get("name_ur"):
        v["name_ur"] = p["name_ur"]
    if dist_km is not None:
        v["distance_km"] = round(dist_km, 2)
        v["walk_minutes"] = round(dist_km * 1000 / 80)
    return v


# ------------------------------------------------------------------ finding things by name

def find_areas(text: str, limit: int = 8) -> List[Dict[str, Any]]:
    """Areas (sectors, phases, societies, neighbourhoods) matching a name, best first."""
    d = data()
    region, q = _region_hint(tokens(text))
    if not q:
        return []
    scored = []
    for a in d.areas:
        if region and a["region"] != region:
            continue
        s = _score(q, a["tokens"], a["parent_tokens"])
        if s >= 0.6:
            scored.append((s, a))
    if not scored:
        return []
    scored.sort(key=lambda x: (-x[0], -x[1]["area_km2"]))
    best = scored[0][0]
    # Several areas can share the best match (an outline and a point, or sectors of one phase).
    picked = [a for s, a in scored if s >= best - 0.02]
    # Drop slivers (a gate or an office mapped under the society's name) next to a real area,
    # and repeats of the same area.
    biggest = max(a["area_km2"] for a in picked)
    picked = [a for a in picked if not (a["area_km2"] < 0.1 and a["area_km2"] * 10 < biggest)]
    out, seen = [], set()
    for a in picked:
        key = (a["name"].lower(), round(a["center"][0], 2), round(a["center"][1], 2))
        if key not in seen:
            seen.add(key)
            out.append(a)
    return out[:limit]


def find_place(text: str) -> Optional[Dict[str, Any]]:
    """A named place (university, hospital, mall …) matching the text."""
    d = data()
    norm = normalize(text)
    for alias, real in ALIASES.items():
        if alias in norm:
            norm = norm.replace(alias, real)
    words = [w for w in norm.split() if w not in STOP]
    region = next((CITY_WORDS[w] for w in words if w in CITY_WORDS), None)
    if not words:
        return None
    best: Tuple[float, Optional[Dict[str, Any]]] = (0.0, None)
    for p in d.places:
        if region and p["region"] != region:
            continue
        hit = sum(1 for w in words if w in p["tokens"])
        if hit < 2 and not (len(words) == 1 and hit == 1):
            continue
        s = hit / len(words) - 0.01 * len(p["tokens"])
        if s > best[0]:
            best = (s, p)
    return best[1] if best[0] >= 0.6 else None


_geocode_cache: Dict[str, Optional[Dict[str, Any]]] = {}
_geocode_lock = threading.Lock()
_last_geocode = 0.0


def geocode_online(text: str) -> Optional[Dict[str, Any]]:
    """Look a name up on OpenStreetMap's Nominatim (cached, ≤ 1 request/second)."""
    global _last_geocode
    if not ONLINE_LOOKUP:
        return None
    key = normalize(text)
    if key in _geocode_cache:
        return _geocode_cache[key]
    with _geocode_lock:
        wait = 1.1 - (time.monotonic() - _last_geocode)
        if wait > 0:
            time.sleep(wait)
        _last_geocode = time.monotonic()
        try:
            r = httpx.get("https://nominatim.openstreetmap.org/search", timeout=8,
                          headers={"User-Agent": "Watan-e-Pak/1.0 (real-estate assistant)"},
                          params={"q": text, "format": "jsonv2", "countrycodes": "pk", "limit": 1, "polygon_geojson": 1,
                                  "polygon_threshold": 0.0003})
            hits = r.json() if r.status_code == 200 else []
        except (httpx.HTTPError, ValueError):
            return None  # don't cache a network failure
    hit = None
    if hits:
        h = hits[0]
        ring: List[List[float]] = []
        g = h.get("geojson") or {}
        if g.get("type") == "Polygon":
            ring = [[c[1], c[0]] for c in g["coordinates"][0]]
        elif g.get("type") == "MultiPolygon":
            ring = [[c[1], c[0]] for c in max(g["coordinates"], key=lambda p: len(p[0]))[0]]
        hit = {"name": h.get("name") or text, "label": h.get("display_name", "")[:160], "lat": float(h["lat"]),
               "lon": float(h["lon"]), "ring": ring[:400], "type": h.get("type"), "source": "nominatim"}
    if len(_geocode_cache) > 2000:  # bounded: drop the oldest half
        for old in list(_geocode_cache)[:1000]:
            _geocode_cache.pop(old, None)
    _geocode_cache[key] = hit
    return hit


# The portal map's own layers (master plans, GIS layers, societies, mega projects) — set by the
# server (mapfind.find); they win over OpenStreetMap names when they match well.
LAYER_LOOKUP: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None


def locate(text: str) -> Optional[Dict[str, Any]]:
    """Where a named place or area is: {name, lat, lon, shape, kind}."""
    if LAYER_LOOKUP is not None:
        hit = LAYER_LOOKUP(text)
        if hit:
            return hit
    place = find_place(text)
    areas = find_areas(text)
    # "Johar Town" is the area, not "Lahore Grammar School Johar Town"; a facility word
    # ("… University", "… Mall") means the place.
    asks_for_place = any(w in FACILITY_WORDS for w in normalize(text).split())
    if place and (not areas or asks_for_place):
        return {"name": place["name"], "kind": KIND_LABELS.get(place["kind"], place["kind"]), "lat": place["lat"],
                "lon": place["lon"], "shape": None, "source": "osm"}
    if areas:
        return _areas_location(areas)
    hit = geocode_online(text)
    if hit:
        shape = Shape([hit["ring"]]) if len(hit["ring"]) >= 3 else None
        return {"name": hit["name"], "kind": hit.get("type") or "place", "lat": hit["lat"], "lon": hit["lon"],
                "shape": shape, "source": "nominatim", "label": hit["label"]}
    return None


def _areas_location(areas: List[Dict[str, Any]]) -> Dict[str, Any]:
    rings = [a["ring"] for a in areas if a.get("ring")]
    circles = [(a["center"][0], a["center"][1], (a.get("radius_m") or 800) / 1000) for a in areas if not a.get("ring")]
    weight = sum(max(a["area_km2"], 0.01) for a in areas)
    lat = sum(a["center"][0] * max(a["area_km2"], 0.01) for a in areas) / weight
    lon = sum(a["center"][1] * max(a["area_km2"], 0.01) for a in areas) / weight
    names = _unique_names(areas)
    return {"name": _join_names(names), "kind": "area", "lat": lat, "lon": lon, "shape": Shape(rings, circles=circles),
            "source": areas[0].get("source", "osm"), "areas": names}


def _unique_names(areas: List[Dict[str, Any]]) -> List[str]:
    seen, names = set(), []
    for a in areas:
        key = normalize(a["name"])
        if key not in seen:
            seen.add(key)
            names.append(a["name"])
    return names


def _join_names(names: List[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _area_shape(text: str) -> Tuple[Optional[Shape], Optional[Dict[str, Any]]]:
    loc = locate(text)
    if not loc:
        return None, None
    if loc.get("shape") is not None:
        return loc["shape"], loc
    return Shape(center=(loc["lat"], loc["lon"]), radius_km=1.0), loc


# ------------------------------------------------------------------ answers

def find_places(kind: Optional[str] = None, name: Optional[str] = None, area: Optional[str] = None,
                near: Optional[str] = None, radius_km: float = 2.0, limit: int = 15) -> Dict[str, Any]:
    """Places of a kind inside an area, or near a place — with a count."""
    if not available():
        return {"error": "Place data is not installed (geodata/*.json.gz)."}
    spec = KINDS.get((kind or "").strip().lower()) if kind else None
    if kind and not spec:
        return {"error": f"Unknown kind '{kind}'. Use one of: {', '.join(KINDS)}"}
    category, kinds, must = spec if spec else (None, None, ())
    scope: Dict[str, Any] = {}
    origin: Optional[Tuple[float, float]] = None
    if area:
        shape, loc = _area_shape(area)
        if not shape:
            return {"found_area": False, "area": area, "count": 0, "places": [],
                    "note": f"I couldn't find an area called '{area}' on the map."}
        scope = {"area": loc["name"], "matched_areas": loc.get("areas") or [loc["name"]], "source": loc["source"]}
        rows = places_in(shape)
    elif near:
        loc = locate(near)
        if not loc:
            return {"found_place": False, "near": near, "count": 0, "places": [],
                    "note": f"I couldn't find '{near}' on the map."}
        origin = (loc["lat"], loc["lon"])
        scope = {"near": loc["name"], "radius_km": radius_km}
        rows = places_in(Shape(center=origin, radius_km=radius_km))
    else:
        return {"error": "Give an area or a place to search near."}
    def matches(p: Dict[str, Any], strict: bool = True) -> bool:
        if category and p["category"] != category:
            return False
        if kinds and p["kind"] not in kinds:
            return False
        low = p["name"].lower()
        if strict and must and not all(m in low for m in must):
            return False
        if name and not all(w in p["tokens"] or w in low for w in tokens(name)):
            return False
        return True

    picked = [p for p in rows if matches(p)]
    if origin:
        picked.sort(key=lambda p: haversine_km(origin[0], origin[1], p["lat"], p["lon"]))
        views = [_place_view(p, haversine_km(origin[0], origin[1], p["lat"], p["lon"])) for p in picked[:limit]]
    else:
        picked.sort(key=lambda p: p["name"])
        views = [_place_view(p) for p in picked[:limit]]
    by_kind = Counter(KIND_LABELS.get(p["kind"], p["kind"]) for p in picked)
    out = {**scope, "kind": kind, "count": len(picked), "by_kind": dict(by_kind), "places": views,
           "note": "Counts are of places mapped on OpenStreetMap; small or new places may be missing.",
           "attribution": ATTRIBUTION}
    if not picked and must:
        # e.g. no school *named* "High School": say how many schools there are at all.
        broader = sorted((p for p in rows if matches(p, strict=False)), key=lambda p: p["name"])
        if broader:
            out["broader"] = {"kind": KIND_LABELS.get(broader[0]["kind"], broader[0]["kind"]), "count": len(broader),
                              "names": [p["name"] for p in broader[:10]],
                              "note": f"None of these is named '{' '.join(must)} …'; the map rarely records school levels."}
    if not picked and area:
        # Nothing inside the area: the closest ones just outside it.
        c = (loc["lat"], loc["lon"])
        near_rows = [p for p in places_in(Shape(center=c, radius_km=5.0)) if matches(p, strict=False)]
        near_rows.sort(key=lambda p: haversine_km(c[0], c[1], p["lat"], p["lon"]))
        if near_rows:
            out["closest_outside_area"] = [_place_view(p, haversine_km(c[0], c[1], p["lat"], p["lon"])) for p in near_rows[:5]]
    return out


def development_level(density_per_km2: float, facilities: int) -> str:
    if density_per_km2 >= 8000 or facilities >= 40:
        return "well developed (dense, many facilities)"
    if density_per_km2 >= 1500 or facilities >= 10:
        return "developing (partly built up)"
    return "early stage or sparsely built"


def area_profile(area: str, properties: Sequence[Any] = ()) -> Dict[str, Any]:
    """Population, development and facilities of an area, plus housing areas around it."""
    if not available():
        return {"error": "Area data is not installed (geodata/*.json.gz)."}
    shape, loc = _area_shape(area)
    if not shape:
        return {"found": False, "area": area, "note": f"I couldn't find an area called '{area}' on the map."}
    places = places_in(shape)
    population = population_in(shape)
    km2 = shape.area_km2
    density = population / km2 if km2 else 0.0
    counts = Counter(p["kind"] for p in places)
    facilities = sum(counts[k] for k in ("school", "college", "university", "hospital", "clinic", "mosque", "mall",
                                         "supermarket", "market", "park", "bank"))
    highlights: Dict[str, List[str]] = {}
    for kind in ("university", "college", "hospital", "mall", "supermarket", "park"):
        names = sorted({p["name"] for p in places if p["kind"] == kind})
        if names:
            highlights[KIND_LABELS[kind]] = names[:6]
    # listings on the portal inside the area
    inside = [p for p in properties if getattr(p, "latitude", None) is not None and shape.contains(p.latitude, p.longitude)]
    per_marla = [p.price / p.marla_area for p in inside if p.marla_area]
    listings = {"count": len(inside)}
    if inside:
        listings["average_price_pkr"] = round(sum(p.price for p in inside) / len(inside))
        if per_marla:
            listings["average_price_per_marla_pkr"] = round(sum(per_marla) / len(per_marla))
        listings["titles"] = [p.title for p in inside[:5]]
    return {
        "found": True,
        "area": loc["name"],
        "matched_areas": loc.get("areas") or [loc["name"]],
        "size_km2": round(km2, 2),
        "population_estimate": population,
        "population_density_per_km2": round(density),
        "development_level": development_level(density, facilities),
        "facility_counts": {KIND_LABELS.get(k, k): n for k, n in counts.most_common() if k in KIND_LABELS},
        "notable_places": highlights,
        "listings_on_portal": listings,
        "nearby_housing_areas": nearby_areas(loc["lat"], loc["lon"], exclude=set(loc.get("areas") or [loc["name"]])),
        "sources": "Population: Kontur 2023 estimate (people living there, from satellite and census data). "
                   "Facilities: places mapped on OpenStreetMap. Development level is derived from these.",
        "attribution": ATTRIBUTION,
    }


def nearby_areas(lat: float, lon: float, radius_km: float = 3.0, exclude: Iterable[str] = (), limit: int = 6) -> List[Dict[str, Any]]:
    """Housing areas around a point, with estimated population and distance."""
    skip = {n.lower() for n in exclude}
    seen, rows = set(), []
    for a in data().areas:
        if a["name"].lower() in skip or a["name"].lower() in seen:
            continue
        dist = haversine_km(lat, lon, a["center"][0], a["center"][1])
        if dist <= radius_km and a.get("kind") in ("residential", "society", "suburb", "neighbourhood", "quarter"):
            seen.add(a["name"].lower())
            rows.append({"name": a["name"], "distance_km": round(dist, 2), "population_estimate": a.get("population"),
                         "size_km2": a.get("area_km2")})
    rows.sort(key=lambda r: (r["distance_km"]))
    return rows[:limit]


def map_markers(lat: float, lon: float, kinds: Sequence[str], radius_km: float = 2.0,
                per_kind: int = 3) -> List[Dict[str, Any]]:
    """The nearest few places of each kind around a point, as map markers."""
    markers: List[Dict[str, Any]] = []
    seen = set()
    for kind in kinds:
        spec = KINDS.get(kind)
        if not spec:
            continue
        category, kind_set, must = spec
        rows = nearest_places(lat, lon, radius_km, category=category, kinds=kind_set, limit=200)
        rows = [r for r in rows if all(m in r["name"].lower() for m in must)][:per_kind]
        for r in rows:
            key = (r["name"], r["latitude"], r["longitude"])
            if key not in seen:
                seen.add(key)
                markers.append({**r, "group": kind})
    return markers


def summary() -> Dict[str, Any]:
    d = data()
    return {"places": len(d.places), "areas": len(d.areas), "population_cells": len(d.cells),
            "regions": {k: v["label"] for k, v in d.regions.items()}, "built": d.built,
            "online_lookup": ONLINE_LOOKUP, "attribution": ATTRIBUTION}
