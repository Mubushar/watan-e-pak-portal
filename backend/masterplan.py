"""
DHA master plans: what the plans show, where, and pictures of them.

Built by ``masterplans/build_masterplans.py`` into ``MASTERPLANS_DIR`` (default
``media/masterplans``): plan outlines and ground transforms, every PDF text label placed on
the ground and classified (sector / block, plot number, plot size, road, park, mosque,
school, commercial …), map tiles, and the full-resolution plan cut into pieces.

Answers: which plan covers a place, what the plan shows around a point, search for a
label, a phase summary (plot sizes, roads, facilities, area statement), readable close-ups
of the plan as PNG, and web facts collected per phase.

Plans © DHA Islamabad-Rawalpindi. Accuracy is about 10–20 m (ground control points).
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
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import envfile  # noqa: F401  (loads backend/.env)
import geo
import storage

DIR = Path(os.getenv("MASTERPLANS_DIR") or Path(__file__).resolve().parent / "media" / "masterplans")
ATTRIBUTION = "Master plan © DHA Islamabad-Rawalpindi"
R = 6378137.0
MARLA_SQFT = 225.0  # DHA Islamabad: 1 marla = 225 sq ft, 1 kanal = 4,500 sq ft

CATEGORY_LABELS = {
    "sector": "Sector / block", "road": "Road / street", "plot_number": "Plot number", "plot_size": "Plot size",
    "park": "Park / green area", "mosque": "Mosque", "education": "School / college", "health": "Health",
    "commercial": "Commercial", "mixed_use": "Mixed use", "apartments": "Apartments", "community": "Club / community",
    "water": "Lake / nullah", "gate": "Gate / entrance", "fuel": "Fuel station", "amenity": "Amenity / utility plot",
    "parking": "Parking", "graveyard": "Graveyard", "infrastructure": "Infrastructure", "dimension": "Dimension",
    "label": "Other label",
}
FACILITY_CATEGORIES = ("mosque", "education", "health", "commercial", "mixed_use", "apartments", "community",
                       "park", "water", "gate", "fuel", "amenity", "graveyard", "parking")
NAMED_CATEGORIES = set(FACILITY_CATEGORIES) | {"sector", "road", "label"}


# ------------------------------------------------------------------ loading

class _Store:
    def __init__(self) -> None:
        self.meta: Dict[str, Dict[str, Any]] = {}
        self.labels: Dict[str, List[Tuple[str, str, float, float, float, int]]] = {}
        self.grid: Dict[str, Dict[Tuple[int, int], List[int]]] = {}
        self.tokens: Dict[str, List[List[str]]] = {}
        self.knowledge: Dict[str, Any] = {}
        self.built: Optional[str] = None


_store: Optional[_Store] = None
_lock = threading.Lock()
CELL = 0.002  # ~200 m


def _key(lat: float, lon: float) -> Tuple[int, int]:
    return int(math.floor(lat / CELL)), int(math.floor(lon / CELL))


def store() -> _Store:
    global _store
    if _store is not None:
        return _store
    with _lock:
        if _store is not None:
            return _store
        s = _Store()
        meta_path, labels_path = DIR / "plans.json", DIR / "labels.json.gz"
        raw_meta = storage.read_seed_asset("media/masterplans/plans.json", str(meta_path))
        if raw_meta:
            meta = json.loads(raw_meta.decode("utf-8"))
            s.built = meta.get("built")
            s.meta = {p["key"]: p for p in meta["plans"]}
        raw_labels = storage.read_seed_asset("media/masterplans/labels.json.gz", str(labels_path))
        if raw_labels:
            with gzip.open(io.BytesIO(raw_labels), "rt", encoding="utf-8") as f:
                for key, rows in json.load(f)["plans"].items():
                    s.labels[key] = [tuple(r) for r in rows]  # type: ignore[misc]
                    grid: Dict[Tuple[int, int], List[int]] = defaultdict(list)
                    for i, r in enumerate(rows):
                        grid[_key(r[2], r[3])].append(i)
                    s.grid[key] = grid
                    s.tokens[key] = [geo.normalize(r[0]).split() for r in rows]
        kpath = DIR / "knowledge.json"
        raw_knowledge = storage.read_seed_asset("media/masterplans/knowledge.json", str(kpath))
        if raw_knowledge:
            s.knowledge = json.loads(raw_knowledge.decode("utf-8"))
        _store = s
        return s


def reload() -> None:
    global _store
    with _lock:
        _store = None


def available() -> bool:
    return bool(store().meta)


# ------------------------------------------------------------------ geometry helpers

def _merc(lat: float, lon: float) -> Tuple[float, float]:
    return math.radians(lon) * R, math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * R


def _to_pixels(meta: Dict[str, Any], lat: float, lon: float) -> Tuple[float, float]:
    X, Y = _merc(lat, lon)
    m = meta["to_pixels"]
    return m[0][0] * X + m[0][1] * Y + m[0][2], m[1][0] * X + m[1][1] * Y + m[1][2]


def _inside(meta: Dict[str, Any], lat: float, lon: float) -> bool:
    b = meta["bounds"]
    if not (b[0] <= lat <= b[2] and b[1] <= lon <= b[3]):
        return False
    return geo.point_in_ring(lat, lon, meta["outline"]) if meta.get("outline") else True


# Plan groups shown as separate sections on the map (each plan's "group" in plans.json).
GROUPS = {"dha": "DHA master plans", "bahria": "Bahria Town master plans", "societies": "Housing society master plans",
          "cda": "Islamabad sectors (CDA)"}


def credit(meta: Optional[Dict[str, Any]]) -> str:
    """The plan's own credit line (Bahria / society plans carry theirs), else the DHA one."""
    return (meta or {}).get("attribution") or ATTRIBUTION


def tile_path(key: str) -> str:
    return f"/masterplans/{key}/tiles/{{z}}/{{x}}/{{y}}.png"


def _public(meta: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "key": meta["key"], "name": meta["name"], "city": meta["city"], "center": meta["center"], "bounds": meta["bounds"],
        "outline": meta.get("outline"), "tile_url": tile_path(meta["key"]) if meta.get("tiles") else None,
        "zoom": meta.get("zoom"), "accuracy": {k: meta["accuracy"].get(k) for k in ("method", "gcps", "rmse_m", "max_m")},
        "label_counts": meta.get("label_counts", {}), "attribution": credit(meta),
        "group": meta.get("group", "dha"), "group_label": GROUPS.get(meta.get("group", "dha"), "Master plans"),
        "society": meta.get("scheme"),
    }


def plans() -> List[Dict[str, Any]]:
    return [_public(m) for m in store().meta.values()]


def find_plan(text: str) -> Optional[Dict[str, Any]]:
    """The plan a name refers to ("DHA 2", "Phase II", "River View North", "ph2")."""
    if not text:
        return None
    s = store()
    if text in s.meta:
        return s.meta[text]
    t = f" {geo.normalize(text)} "
    best: Tuple[int, Optional[Dict[str, Any]]] = (0, None)
    for m in s.meta.values():
        for alias in [m["name"], m["key"], *m.get("aliases", [])]:
            a = geo.normalize(alias)
            if a and f" {a} " in t and len(a) > best[0]:
                best = (len(a), m)
    return best[1]


def plans_at(lat: float, lon: float) -> List[Dict[str, Any]]:
    return [m for m in store().meta.values() if _inside(m, lat, lon)]


def overlays_at(lat: float, lon: float, margin_km: float = 1.0) -> List[Dict[str, Any]]:
    """Map overlays for the plans at (or within ``margin_km`` of) a point."""
    out = []
    for m in store().meta.values():
        if not m.get("tiles"):
            continue
        b = m["bounds"]
        d = margin_km / 111.0
        if b[0] - d <= lat <= b[2] + d and b[1] - d <= lon <= b[3] + d:
            out.append({"key": m["key"], "name": f"{m['name']} master plan", "tile_url": tile_path(m["key"]),
                        "bounds": b, "min_zoom": m["zoom"][0], "max_native_zoom": m["zoom"][1],
                        "attribution": credit(m), "group": m.get("group", "dha")})
    return out


# ------------------------------------------------------------------ labels

def _label_view(key: str, r: Sequence[Any], origin: Optional[Tuple[float, float]] = None) -> Dict[str, Any]:
    v = {"text": r[0], "category": r[1], "kind": CATEGORY_LABELS.get(r[1], r[1]), "plan": store().meta[key]["name"],
         "plan_key": key, "latitude": r[2], "longitude": r[3]}
    if origin:
        v["distance_m"] = round(geo.haversine_km(origin[0], origin[1], r[2], r[3]) * 1000)
    return v


def labels_near(lat: float, lon: float, radius_m: float = 150.0, key: Optional[str] = None,
                categories: Optional[Iterable[str]] = None) -> List[Dict[str, Any]]:
    s = store()
    cats = set(categories) if categories else None
    keys = [key] if key else [m["key"] for m in s.meta.values()
                              if m["bounds"][0] - 0.01 <= lat <= m["bounds"][2] + 0.01 and m["bounds"][1] - 0.01 <= lon <= m["bounds"][3] + 0.01]
    span = int(math.ceil(radius_m / 1000 / 111.0 / CELL)) + 1
    ci, cj = _key(lat, lon)
    rows = []
    for k in keys:
        grid, labels = s.grid.get(k, {}), s.labels.get(k, [])
        for i in range(ci - span, ci + span + 1):
            for j in range(cj - span, cj + span + 1):
                for idx in grid.get((i, j), ()):
                    r = labels[idx]
                    if cats and r[1] not in cats:
                        continue
                    d = geo.haversine_km(lat, lon, r[2], r[3]) * 1000
                    if d <= radius_m:
                        rows.append((d, k, r))
    rows.sort(key=lambda x: x[0])
    return [_label_view(k, r, (lat, lon)) for d, k, r in rows]


def _context(key: str, lat: float, lon: float) -> Optional[str]:
    """The nearest named road or sector label (for "plot 23 — near Street 13")."""
    for v in labels_near(lat, lon, 180, key, ("road", "sector")):
        t = v["text"].strip()
        # a named or numbered road / block, not "10' Wide Sidewalk" or a bare "STREET"
        if len(t) <= 40 and re.search(r"\d|[A-Za-z]{4,}\s+[A-Za-z]", t) and \
                not re.search(r"(?i)sidewalk|walkway|service|^\(|^\d|^(street|road|lane)$|wide\)?$", t):
            return t
    return None


def search(q: str, plan: Optional[str] = None, category: Optional[str] = None, limit: int = 20) -> Dict[str, Any]:
    """Labels matching words ("C10", "Jinnah Blvd", "masjid", "plot 23")."""
    s = store()
    meta = find_plan(plan) if plan else None
    keys = [meta["key"]] if meta else list(s.meta)
    words = [w for w in geo.normalize(q).split() if w not in ("dha", "phase", "plot", "no", "number", "the", "in", "of")]
    if meta:  # drop words that only name the plan
        plan_words = set(geo.normalize(" ".join([meta["name"], *meta.get("aliases", [])])).split())
        words = [w for w in words if w not in plan_words] or words
    hits = []
    for k in keys:
        for r, toks in zip(s.labels.get(k, []), s.tokens.get(k, [])):
            if category and r[1] != category:
                continue
            if not words:
                continue
            hit = sum(1 for w in words if w in toks or (len(w) >= 4 and any(t.startswith(w) for t in toks)))
            if hit == len(words):
                hits.append((len(toks) - hit, k, r))
    hits.sort(key=lambda x: x[0])
    rows = []
    for _, k, r in hits[:limit]:
        v = _label_view(k, r)
        ctx = _context(k, r[2], r[3])
        if ctx and ctx != r[0]:
            v["near"] = ctx
        rows.append(v)
    return {"query": q, "plan": meta["name"] if meta else None, "count": len(hits), "results": rows,
            "note": "Positions are from the georeferenced master plan (about 10–20 m accuracy).",
            "attribution": credit(meta)}


def at(lat: float, lon: float, radius_m: float = 200.0) -> Dict[str, Any]:
    """What the master plan shows around a point."""
    here = plans_at(lat, lon)
    near = labels_near(lat, lon, radius_m)
    by_cat: Dict[str, List[str]] = defaultdict(list)
    for v in near:
        if v["category"] in ("dimension", "infrastructure", "label", "plot_number"):
            continue
        if v["text"] not in by_cat[v["kind"]] and len(by_cat[v["kind"]]) < 8:
            by_cat[v["kind"]].append(v["text"])
    sizes = Counter(plot_size(v["text"]) for v in near if v["category"] == "plot_size")
    sizes.pop(None, None)  # type: ignore[arg-type]
    plots = [v["text"] for v in near if v["category"] == "plot_number"][:20]
    return {"inside_plans": [m["name"] for m in here], "radius_m": radius_m, "features": dict(by_cat),
            "plot_sizes": [{"size": k, "count": n} for k, n in sizes.most_common(6)], "plot_numbers": plots,
            "infrastructure_marks": sum(1 for v in near if v["category"] == "infrastructure"),
            "note": "From the georeferenced master plan (about 10–20 m accuracy); what is built may differ.",
            "attribution": "; ".join(sorted({credit(m) for m in here})) or ATTRIBUTION}


SIZE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*'?\s*[xX×]\s*(\d+(?:\.\d+)?)")


def plot_size(text: str) -> Optional[str]:
    """ "50'X90'" -> "50'×90' (1 kanal)", "35x70" -> "35'×70' (≈10.9 marla)"."""
    m = SIZE_RE.search(text)
    if not m:
        k = re.search(r"(\d+(?:\.\d+)?)\s*(KANAL|MARLA)", text.upper())
        return f"{k.group(1)} {k.group(2).lower()}" if k else None
    a, b = sorted((float(m.group(1)), float(m.group(2))))
    if a < 15 or b > 400:  # drains, poles, signs
        return None
    sqft = a * b
    marla = sqft / MARLA_SQFT
    size = f"{int(marla / 20) if marla % 20 == 0 else round(marla / 20, 1)} kanal" if marla >= 20 else f"≈{round(marla, 1):g} marla"
    return f"{a:g}'×{b:g}' ({size})"


def summary(plan: str) -> Dict[str, Any]:
    """A phase at a glance: plot sizes, sectors / blocks, roads, facilities, area statement, web facts."""
    meta = find_plan(plan)
    if not meta:
        return {"error": f"No master plan for '{plan}'. Available: {', '.join(m['name'] for m in store().meta.values())}"}
    k = meta["key"]
    rows = store().labels.get(k, [])
    sizes = Counter(plot_size(r[0]) for r in rows if r[1] == "plot_size")
    sizes.pop(None, None)  # type: ignore[arg-type]

    def names(cat: str, n: int = 15) -> List[str]:
        seen: Dict[str, int] = Counter(r[0].strip(" ,/(") for r in rows if r[1] == cat)  # type: ignore[assignment]
        return [t for t, _ in Counter(seen).most_common(n)]

    def where(cat: str, n: int = 12) -> List[str]:
        """Facilities with the street they are on: "MASJID — near STREET-44"."""
        out, seen = [], set()
        for r in rows:
            if r[1] != cat:
                continue
            ctx = _context(k, r[2], r[3])
            item = f"{r[0].strip(' ,/(')} — near {ctx}" if ctx else r[0].strip(" ,/(")
            if item.lower() not in seen:
                seen.add(item.lower())
                out.append(item)
            if len(out) >= n:
                break
        return out

    roads = [t for t in names("road", 60) if re.search(r"[A-Za-z]{4,}", t) and not re.fullmatch(r"(?i)(street|road|lane|wide|service.*)", t)]
    notes = [t for t in meta.get("sheet_text", []) if re.search(r"(?i)area|kanal|acre|total|residential|commercial|legend|plots?|amenit|park|school|mosque|graveyard", t)]
    return {
        "plan": meta["name"], "city": meta["city"], "key": k,
        "accuracy": meta["accuracy"],
        "label_counts": {CATEGORY_LABELS.get(c, c): n for c, n in Counter(r[1] for r in rows).most_common()},
        "plot_sizes": [{"size": s, "labels_on_plan": n} for s, n in sizes.most_common(10)],
        "plot_numbers_on_plan": sum(1 for r in rows if r[1] == "plot_number"),
        "sectors_blocks": names("sector", 30),
        "named_roads": roads[:30],
        "facilities": {CATEGORY_LABELS[c]: where(c) for c in FACILITY_CATEGORIES if c != "parking" and names(c, 1)},
        "sheet_notes": notes[:40],
        "web_facts": store().knowledge.get(k),
        "note": "From the master plan (plans change; what is built may differ). Plot sizes in marla use 225 sq ft per marla.",
        "attribution": credit(meta),
    }


# ------------------------------------------------------------------ pictures

@lru_cache(maxsize=48)
def _chunk(key: str, cx: int, cy: int):
    from PIL import Image
    p = DIR / key / "source" / f"{cx}_{cy}.png"
    return Image.open(p).convert("RGBA") if p.exists() else None


def snapshot(plan: str, lat: float, lon: float, radius_m: float = 250.0, label: Optional[str] = None,
             max_px: int = 1100) -> Optional[bytes]:
    """A readable PNG close-up of the master plan around a point, with a marker and scale bar."""
    from PIL import Image, ImageDraw, ImageFont

    meta = find_plan(plan) or (plans_at(lat, lon) or [None])[0]
    if not meta:
        return None
    k, size, chunk = meta["key"], meta["source_size"], meta.get("chunk", 1024)
    px, py = _to_pixels(meta, lat, lon)
    rad = max(60.0, radius_m / meta["m_per_px"])
    x0, y0, x1, y1 = int(px - rad), int(py - rad), int(px + rad), int(py + rad)
    if x1 < 0 or y1 < 0 or x0 > size[0] or y0 > size[1]:
        return None
    if (x1 - x0) > 4000 and (DIR / k / "preview.png").exists():  # very wide view: use the preview
        prev = Image.open(DIR / k / "preview.png").convert("RGBA")
        f = prev.width / size[0]
        canvas = prev.crop((int(x0 * f), int(y0 * f), int(x1 * f), int(y1 * f)))
    else:
        canvas = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
        for cy in range(max(0, y0) // chunk, min(size[1] - 1, y1) // chunk + 1):
            for cx in range(max(0, x0) // chunk, min(size[0] - 1, x1) // chunk + 1):
                piece = _chunk(k, cx, cy)
                if piece is not None:  # paste clips pieces that start left of / above the crop
                    canvas.paste(piece, (cx * chunk - x0, cy * chunk - y0), piece)
    img = Image.new("RGB", canvas.size, (255, 255, 255))
    img.paste(canvas, (0, 0), canvas)
    # Fit the long side to max_px: shrink big crops, enlarge small ones (up to 3×) so text is readable.
    scale = min(3.0, max_px / max(img.size))
    if abs(scale - 1.0) > 0.01:
        img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.LANCZOS)
    d = ImageDraw.Draw(img)
    cxp, cyp = (px - x0) * scale, (py - y0) * scale
    # a ring (not a dot) so the plot's own text stays readable
    d.ellipse((cxp - 29, cyp - 29, cxp + 29, cyp + 29), outline=(255, 255, 255), width=9)  # halo: visible on any colour
    d.ellipse((cxp - 26, cyp - 26, cxp + 26, cyp + 26), outline=(29, 78, 216), width=5)
    d.ellipse((cxp - 4, cyp - 4, cxp + 4, cyp + 4), fill=(29, 78, 216), outline=(255, 255, 255))
    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except OSError:
        font = ImageFont.load_default()
    # caption + scale bar
    bar_m = 50 if radius_m <= 200 else 100 if radius_m <= 500 else 250 if radius_m <= 1200 else 500
    bar_px = bar_m / meta["m_per_px"] * scale
    h = 34
    d.rectangle((0, img.height - h, img.width, img.height), fill=(255, 255, 255))
    caption = f"{meta['name']} master plan" + (f" — {label}" if label else "")
    d.text((10, img.height - h + 7), caption[:90], fill=(15, 31, 23), font=font)
    bx = img.width - bar_px - 70
    d.line((bx, img.height - 12, bx + bar_px, img.height - 12), fill=(15, 31, 23), width=4)
    d.text((bx + bar_px + 8, img.height - h + 7), f"{bar_m} m", fill=(15, 31, 23), font=font)
    note = "© DHA Islamabad-Rawalpindi · positions approx. 10-20 m"
    d.rectangle((0, 0, d.textlength(note, font=font) + 16, 30), fill=(255, 255, 255))
    d.text((8, 6), note, fill=(90, 90, 90), font=font)
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


# ------------------------------------------------------------------ web facts

def collect_knowledge(keys: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """Ask the web (OpenAI web search) about each phase; saved to knowledge.json with sources."""
    import web_lookup

    s = store()
    out = dict(s.knowledge)
    for k in keys or list(s.meta):
        m = s.meta[k]
        q = (f"{m['name']} {m['city']} (DHA Islamabad-Rawalpindi), Pakistan: development and possession status, "
             f"approvals, sectors or blocks, plot sizes offered, main facilities (commercial areas, schools, hospitals, "
             f"parks, mosques, clubs), access roads, and recent news or price trends.")
        try:
            r = web_lookup.lookup(q)
            out[k] = {"facts": r["answer"], "sources": r["sources"], "collected": time.strftime("%Y-%m-%d")}
        except Exception as exc:  # keep going; report per phase
            out[k] = {**out.get(k, {}), "error": str(exc)}
    knowledge_bytes = json.dumps(out, ensure_ascii=False, indent=1).encode("utf-8")
    if not storage.put_asset("seed/media/masterplans/knowledge.json", "application/json", knowledge_bytes):
        (DIR / "knowledge.json").write_bytes(knowledge_bytes)
    s.knowledge = out
    return out


# ------------------------------------------------------------------ GIS layers

def _label_geometry(meta: Dict[str, Any]) -> Tuple[float, float]:
    """(metres per PDF point, rotation of the plan image on the ground in degrees CCW)."""
    m_per_pt = float((meta.get("pdf_alignment") or {}).get("scale") or 0) * float(meta.get("m_per_px") or 0)
    g = meta.get("to_ground")
    rot = math.degrees(math.atan2(g[1][0], g[0][0])) if g else 0.0
    return m_per_pt, rot


def geojson_labels(key: str, categories: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """The plan's text labels as GeoJSON points.

    ``angle`` is the text direction on the plan image (degrees CCW); ``rot`` is that direction
    on the map (north-up, degrees CCW) and ``size_m`` the text height on the ground in metres,
    so a map can draw each label at the plan's own scale and orientation."""
    cats = set(categories) if categories else None
    meta = store().meta.get(key) or {}
    m_per_pt, plan_rot = _label_geometry(meta)
    feats = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [r[3], r[2]]},
              "properties": {"text": r[0], "category": r[1], "font_size": r[4], "angle": r[5],
                             "rot": round(r[5] + plan_rot, 1), "size_m": round(r[4] * m_per_pt, 2)}}
             for r in store().labels.get(key, []) if not cats or r[1] in cats]
    return {"type": "FeatureCollection", "features": feats}


def outline_geojson(meta: Dict[str, Any]) -> Dict[str, Any]:
    ring = [[p[1], p[0]] for p in meta.get("outline", [])]
    if ring and ring[0] != ring[-1]:
        ring.append(ring[0])
    return {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]},
                                                       "properties": {"name": meta["name"], "source": meta.get("pdf")}}]}


LABEL_GROUPS = [
    # Off by default: each group is thousands of points (the plan tiles already show the
    # text), and visible layers are embedded in every scheme's HTML map.
    ("names & facilities", sorted(NAMED_CATEGORIES), False),
    ("plot numbers & sizes", ["plot_number", "plot_size"], False),
    ("engineering marks & dimensions", ["infrastructure", "dimension"], False),
]
