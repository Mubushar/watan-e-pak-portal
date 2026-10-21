"""
The portal map's own layers as a gazetteer: master plans (by name, alias and society), uploaded GIS
layers and their named features, housing societies and mega projects. ``geo.locate`` asks here first,
so every tool that looks a place up ("zoom to Park View", "listings near Sector G-13", "route to
Bahria Phase 7") finds what is drawn on the map before OpenStreetMap's names — "Park View" is the
Park View City master plan, not "Lake View Park".

    find(text)            -> the best layer for a name, as a geo.locate location (or None)
    catalogue(q, city, …) -> every layer on the map, filtered, for the assistant (GET /map/layers)
"""
from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import geo
import gis
import masterplan
import megaprojects

# Words that name a kind of place rather than which one: a match needs one of the other words.
WEAK = {"phase", "sector", "block", "city", "extension", "ext", "part", "new", "chs", "echs", "cooperative", "co",
        "employees", "plan", "master", "map", "layer", "zone", "sub", "road", "avenue", "garden", "gardens", "enclave",
        "residencia", "villas", "valley", "homes", "estate", "colony", "approval", "cancelled"}
# Layers generated from master plans (the plan itself stands for them).
PLAN_LAYER_TYPES = {"master_plan", "boundary", "annotation"}


def _words(text: str) -> Tuple[Optional[str], List[str]]:
    words = geo.tokens(text)
    region, rest = geo._region_hint(words)
    return region, rest


FACILITY = {"mosque", "masjid", "school", "park", "mall", "hospital", "university", "college", "market", "plaza", "hotel",
            "stadium", "station", "airport", "chowk", "gate"}
# Words for a part of a plan, looked up in its text ("DHA 2 C10 commercial", "plot 23 street 13").
PART = {"commercial", "plot", "plots", "street", "st", "lane", "boulevard", "blvd", "markaz", "mosque", "masjid", "school",
        "park", "chowk", "gate", "main", "no", "number", "corner", "facing"}


def _part_word(w: str) -> bool:
    return w in WEAK or w in PART or len(w) <= 2 or any(c.isdigit() for c in w)


def _region_of(city: Optional[str]) -> Optional[str]:
    return geo.CITY_WORDS.get((city or "").strip().lower())


def _score(q: Sequence[str], phrase: str, whole: bool = False) -> float:
    """How well the query words name this phrase: 0 (no) … 2 (exactly). ``whole``: every word of
    the phrase must be asked for (names without aliases — "Giga Mall" isn't "Giga Mall Extension")."""
    p = set(geo.tokens(phrase)) - set(geo.CITY_WORDS)
    qs = set(q)
    inter = p & qs
    if not inter or not (inter - WEAK - {w for w in inter if w.isdigit()}):
        return 0.0
    # Every word asked for that the phrase lacks must be a generic one ("Lake View Park" isn't "Park View"),
    # or name a part of it (a sector letter, a block / plot number) that is looked up on the plan.
    if any(not _part_word(w) for w in qs - p):
        return 0.0
    if whole and inter != p:
        return 0.0
    # A number asked for (phase 7, G-13) must be the phrase's number.
    q_nums = {w for w in qs if any(c.isdigit() for c in w)}
    p_nums = {w for w in p if any(c.isdigit() for c in w)}
    if q_nums and p_nums and not (q_nums & p_nums):
        return 0.0
    cov_q = len(inter) / len(qs)
    cov_p = len(inter) / len(p)
    # The whole phrase was named (the rest names a part of it), or all that was asked is most of the phrase.
    if cov_p == 1 or (cov_q == 1 and cov_p >= 0.5):
        return cov_q + cov_p
    return 0.0


def _bounds(points: Iterable[Sequence[float]]) -> Optional[List[float]]:
    pts = [p for p in points if len(p) >= 2]
    if not pts:
        return None
    return [min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)]


def _geom_points(g: Dict[str, Any]) -> List[List[float]]:
    """[lat, lon] points of a GeoJSON geometry (lon, lat)."""
    t, c = g.get("type"), g.get("coordinates")
    if not c:
        return []
    if t == "Point":
        return [[c[1], c[0]]]
    if t in ("LineString", "MultiPoint"):
        return [[x[1], x[0]] for x in c]
    if t in ("Polygon", "MultiLineString"):
        return [[x[1], x[0]] for ring in c for x in ring]
    if t == "MultiPolygon":
        return [[x[1], x[0]] for poly in c for ring in poly for x in ring]
    return []


# ------------------------------------------------------------------ the candidates

def _plans() -> List[Dict[str, Any]]:
    out = []
    for m in masterplan.store().meta.values():
        b = m.get("bounds")
        if not b:
            continue
        out.append({"kind": "master plan", "name": m["name"], "key": m["key"], "city": m.get("city"),
                    "group": masterplan.GROUPS.get(m.get("group", "dha"), m.get("group")),
                    "phrases": [m["name"], *m.get("aliases", []), *([m["society"]] if m.get("society") else [])],
                    "center": m.get("center") or [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2], "bounds": b,
                    "ring": m.get("outline"), "accuracy_m": (m.get("accuracy") or {}).get("rmse_m")})
    return out


def _gis_layers() -> List[Dict[str, Any]]:
    """Uploaded / drawn layers (not the ones made from master plans) and their named features."""
    out = []
    plan_names = tuple(m["name"] for m in masterplan.store().meta.values())
    for l in gis.GIS_LAYERS:
        if not getattr(l, "published", True) or (l.layer_type in PLAN_LAYER_TYPES and l.name.startswith(plan_names)):
            continue
        feats = (l.geojson or {}).get("features") or []
        pts = [p for f in feats for p in _geom_points(f.get("geometry") or {})]
        if not pts:
            continue
        b = _bounds(pts)
        out.append({"kind": f"GIS layer ({l.layer_type.replace('_', ' ')})", "name": l.name, "key": l.id, "city": None,
                    "phrases": [l.name], "center": [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2], "bounds": b,
                    "features": len(feats)})
        for f in feats[:400]:
            props = f.get("properties") or {}
            name = props.get("name") or props.get("title") or props.get("label")
            fp = _geom_points(f.get("geometry") or {})
            if not name or not fp:
                continue
            fb = _bounds(fp)
            ring = fp if (f.get("geometry") or {}).get("type") == "Polygon" else None
            out.append({"kind": f"feature in {l.name}", "name": str(name), "key": l.id, "city": None, "phrases": [str(name)],
                        "center": [(fb[0] + fb[2]) / 2, (fb[1] + fb[3]) / 2], "bounds": fb, "ring": ring})
    return out


def _societies() -> List[Dict[str, Any]]:
    try:
        import server
    except ImportError:  # pragma: no cover - tests import differently
        return []
    out = []
    for s in server.housing_schemes_db:
        if s.latitude is None or s.longitude is None:
            continue
        out.append({"kind": "housing society", "name": s.name, "key": s.id, "city": server.city_name(s.city_id),
                    "phrases": [s.name], "center": [s.latitude, s.longitude], "bounds": None})
    return out


def _projects() -> List[Dict[str, Any]]:
    out = []
    for p in megaprojects.search():
        c = p.get("center")
        if not c:
            continue
        out.append({"kind": f"mega project ({p.get('type_label', p.get('type', ''))})", "name": p["name"], "key": p["id"],
                    "city": p.get("city"), "phrases": [p["name"]], "center": c, "bounds": p.get("bounds")})
    return out


def _all() -> List[Dict[str, Any]]:
    return [*_plans(), *_gis_layers(), *_projects(), *_societies()]


# ------------------------------------------------------------------ lookups

def _ranked(text: str, items: List[Dict[str, Any]]) -> List[Tuple[float, Dict[str, Any]]]:
    region, q = _words(text)
    if not q:
        return []
    out = []
    for it in items:
        if region and it.get("city") and _region_of(it["city"]) not in (None, region):
            continue
        whole = it["kind"] != "master plan"  # plans have aliases for their short names
        s = max((_score(q, ph, whole) for ph in it["phrases"] if ph), default=0.0)
        if s <= 0:
            continue
        # Prefer what is drawn (a plan's outline) over a point, and a whole plan over its extensions.
        s += 0.05 if it["kind"] == "master plan" else 0.0
        s -= 0.01 * len(geo.tokens(it["name"]))
        out.append((s, it))
    out.sort(key=lambda x: -x[0])
    return out


def find(text: str) -> Optional[Dict[str, Any]]:
    """The map layer a name means, as a ``geo.locate`` location — None when nothing on the map matches well."""
    ranked = _ranked(text, _all())
    if not ranked or ranked[0][0] < 1.25:
        return None
    it = ranked[0][1]
    # Several plans fit equally ("DHA", "Bahria phase"): don't guess — the caller asks / searches wider.
    if len(ranked) > 1 and ranked[1][0] >= ranked[0][0] - 0.02 and ranked[1][1]["name"] != it["name"]:
        return None
    if it["kind"] == "master plan":
        spot = _on_plan(text, it)
        if spot:
            return spot
        # "Faisal Mosque" is a mosque, not Faisal Town: a facility the plan's text doesn't have is a place elsewhere.
        _, q = _words(text)
        named = set().union(*(set(geo.tokens(ph)) for ph in it["phrases"] if ph))
        if any(w in FACILITY for w in q if w not in named):
            return None
    ring = it.get("ring") if it.get("ring") and len(it["ring"]) >= 3 else None
    b = it.get("bounds")
    shape = geo.Shape([ring]) if ring else (geo.Shape([[[b[0], b[1]], [b[0], b[3]], [b[2], b[3]], [b[2], b[1]]]]) if b and b[0] != b[2] else None)
    return {"name": it["name"], "kind": it["kind"], "lat": round(it["center"][0], 6), "lon": round(it["center"][1], 6),
            "shape": shape, "source": "portal map", "bounds": b, "layer": it.get("key")}


def _on_plan(text: str, plan: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """"DHA Phase II sector F": the part of the plan named after the plan's own name (its text label)."""
    _, q = _words(text)
    named = set().union(*(set(geo.tokens(ph)) for ph in plan["phrases"] if ph))
    rest = [w for w in q if w not in named]
    if not rest:
        return None
    for words in (rest, [w for w in rest if w not in WEAK], [w for w in rest if w not in WEAK and w not in PART]):
        if not words:
            continue
        hits = masterplan.search(" ".join(words), plan=plan["key"], limit=1).get("results") or []
        if hits:
            h = hits[0]
            return {"name": f"{h['text']}, {plan['name']}", "kind": f"{h.get('kind', 'label')} on the master plan", "lat": h["latitude"],
                    "lon": h["longitude"], "shape": None, "source": "portal map", "bounds": None, "layer": plan["key"]}
    return None


def catalogue(q: Optional[str] = None, city: Optional[str] = None, kind: Optional[str] = None,
              lat: Optional[float] = None, lon: Optional[float] = None, limit: int = 60) -> Dict[str, Any]:
    """Everything on the portal's map, for the assistant: counts by kind / group / city, and the layers
    matching ``q`` (a name), ``city``, ``kind`` or nearest to ``lat, lon``."""
    items = _all()
    counts: Dict[str, int] = {}
    plan_groups: Dict[str, Dict[str, int]] = {}
    for it in items:
        k = it["kind"].split(" (")[0] if not it["kind"].startswith("feature in") else "GIS feature"
        counts[k] = counts.get(k, 0) + 1
        if it["kind"] == "master plan":
            g = plan_groups.setdefault(it.get("group") or "Master plans", {})
            g[it.get("city") or "?"] = g.get(it.get("city") or "?", 0) + 1
    pool = items
    if kind:
        pool = [it for it in pool if kind.lower() in it["kind"].lower()]
    if city:
        region = _region_of(city)
        pool = [it for it in pool if (it.get("city") or "").lower() == city.lower() or (region and _region_of(it.get("city")) == region)]
    if q:
        ranked = _ranked(q, pool)
        if not ranked:  # looser: any word of the name
            qs = set(_words(q)[1]) - WEAK
            ranked = [(len(qs & set(geo.tokens(" ".join(it["phrases"])))), it) for it in pool]
            ranked = [r for r in ranked if r[0] > 0]
            ranked.sort(key=lambda x: -x[0])
        pool = [it for _, it in ranked]
    elif lat is not None and lon is not None:
        pool = sorted(pool, key=lambda it: (it["center"][0] - lat) ** 2 + ((it["center"][1] - lon) * math.cos(math.radians(lat))) ** 2)
    rows = []
    for it in pool[: max(1, min(limit, 200))]:
        row = {"name": it["name"], "kind": it["kind"], "city": it.get("city"), "center": [round(x, 6) for x in it["center"]]}
        if it.get("group"):
            row["group"] = it["group"]
        if it.get("bounds"):
            row["bounds"] = [round(x, 6) for x in it["bounds"]]
        if it.get("accuracy_m"):
            row["accuracy_m"] = it["accuracy_m"]
        if it.get("features"):
            row["features"] = it["features"]
        if lat is not None and lon is not None:
            row["distance_km"] = round(geo.haversine_km(lat, lon, it["center"][0], it["center"][1]), 2)
        rows.append(row)
    return {"total_on_map": len(items), "counts": counts, "master_plans_by_group_and_city": plan_groups,
            "matched": len(pool), "results": rows,
            "note": "Master plans are georeferenced drawings (about 10–20 m accuracy); what is built may differ."}
