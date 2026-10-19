"""
Infrastructure & development mega projects that affect land prices: ring roads, motorways,
expressways, mass transit, rail, new sectors / subdivisions, industrial & special economic
zones, airports and business districts (``geodata/pk_megaprojects.json``).

Each project has a geometry — a ``line`` (path of [lat, lon]), a ``polygon`` (ring of
[lat, lon]) or a ``point`` (centre + radius_km) — and an ``impact_radius_km``: how far its
price effect reaches. ``near()`` finds the projects that reach a point or a drawn area and
how strongly (distance-decayed, by status and expected uplift).
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

DATA = Path(__file__).with_name("geodata") / "pk_megaprojects.json"

TYPE_LABELS = {
    "ring_road": "Ring road", "motorway": "Motorway", "expressway": "Expressway / avenue",
    "transit": "Mass transit", "railway": "Railway", "subdivision": "New sector / city",
    "industrial": "Industrial / economic zone", "airport": "Airport", "cbd": "Business district",
    "tower": "High-rise & mixed-use project", "mall": "Shopping mall",
}
STATUS_LABELS = {"planned": "Planned", "approved": "Approved", "under_construction": "Under construction", "completed": "Recently completed"}
# How much a project's status counts towards price effect today (0-1).
STATUS_WEIGHT = {"under_construction": 1.0, "completed": 0.85, "approved": 0.6, "planned": 0.4}
UPLIFT_WEIGHT = {"high": 1.0, "medium": 0.65, "low": 0.35}


@lru_cache(maxsize=1)
def _load() -> Dict[str, Any]:
    with DATA.open(encoding="utf-8") as f:
        return json.load(f)


def note() -> str:
    return _load().get("note", "")


def all_projects() -> List[Dict[str, Any]]:
    """Infrastructure projects from the data file, plus the new high-rise / mixed-use projects whose
    unit inventories the portal tracks (geodata/pk_project_inventory.json)."""
    try:
        import project_inventory

        extra = project_inventory.as_megaprojects()
    except Exception:
        extra = []
    try:
        import seed_media

        photos = seed_media.load().get("megaprojects") or {}
    except Exception:
        photos = {}
    base = [{**p, "image": photos[p["id"]]["url"], "image_credit": photos[p["id"]].get("credit")} if p["id"] in photos else p
            for p in _load()["projects"]]
    return base + extra


def get(project_id: str) -> Optional[Dict[str, Any]]:
    return next((p for p in all_projects() if p["id"] == project_id), None)


def _km_xy(lat0: float) -> Tuple[float, float]:
    return 111.32 * math.cos(math.radians(lat0)), 110.57


def _seg_dist_km(p: Tuple[float, float], a: List[float], b: List[float]) -> float:
    kx, ky = _km_xy(p[0])
    px, py = p[1] * kx, p[0] * ky
    ax, ay, bx, by = a[1] * kx, a[0] * ky, b[1] * kx, b[0] * ky
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _in_ring(lat: float, lon: float, ring: List[List[float]]) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        yi, xi = ring[i]
        yj, xj = ring[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def distance_km(project: Dict[str, Any], lat: float, lon: float) -> float:
    """Distance from a point to the project's footprint (0 when inside it)."""
    g = project["geometry"]
    if g["type"] == "point":
        c = g["center"]
        kx, ky = _km_xy(lat)
        return max(0.0, math.hypot((lon - c[1]) * kx, (lat - c[0]) * ky) - g.get("radius_km", 0))
    pts = g["path"] if g["type"] == "line" else g["ring"]
    if g["type"] == "polygon" and _in_ring(lat, lon, pts):
        return 0.0
    segs = zip(pts, pts[1:] + ([pts[0]] if g["type"] == "polygon" else []))
    return min((_seg_dist_km((lat, lon), a, b) for a, b in segs), default=float("inf"))


def _bbox(project: Dict[str, Any]) -> Tuple[float, float, float, float]:
    g = project["geometry"]
    if g["type"] == "point":
        c, r = g["center"], g.get("radius_km", 1) / 111
        return c[0] - r, c[1] - r, c[0] + r, c[1] + r
    pts = g["path"] if g["type"] == "line" else g["ring"]
    return min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)


def summary(p: Dict[str, Any]) -> Dict[str, Any]:
    """A project with labels and a centre / bounds, for lists and maps."""
    s, w, n, e = _bbox(p)
    return {**p, "type_label": TYPE_LABELS.get(p["type"], p["type"]), "status_label": STATUS_LABELS.get(p["status"], p["status"]),
            "bounds": [round(s, 5), round(w, 5), round(n, 5), round(e, 5)],
            "center": [round((s + n) / 2, 5), round((w + e) / 2, 5)]}


def search(type: Optional[str] = None, status: Optional[str] = None, province: Optional[str] = None,
           city: Optional[str] = None, q: Optional[str] = None) -> List[Dict[str, Any]]:
    out = []
    for p in all_projects():
        if type and p["type"] not in type.split(","):
            continue
        if status and p["status"] not in status.split(","):
            continue
        if province and province.lower() not in p.get("province", "").lower():
            continue
        if city and city.lower() != p.get("city", "").lower():
            continue
        if q and q.lower() not in f"{p['name']} {p.get('city', '')} {p.get('summary', '')}".lower():
            continue
        out.append(summary(p))
    # the portal's order (priority.py): projects in the DHA / Bahria phases first, then by city
    import priority

    out.sort(key=lambda p: priority.project_key(p.get("scheme"), p.get("city")))
    return out


def geojson(projects: Optional[Iterable[Dict[str, Any]]] = None) -> Dict[str, Any]:
    feats = []
    for p in projects if projects is not None else all_projects():
        g = p["geometry"]
        if g["type"] == "line":
            geom = {"type": "LineString", "coordinates": [[x[1], x[0]] for x in g["path"]]}
        elif g["type"] == "polygon":
            ring = [[x[1], x[0]] for x in g["ring"]]
            geom = {"type": "Polygon", "coordinates": [ring + [ring[0]]]}
        else:
            geom = {"type": "Point", "coordinates": [g["center"][1], g["center"][0]]}
        props = {k: v for k, v in p.items() if k != "geometry"}
        feats.append({"type": "Feature", "id": p["id"], "geometry": geom, "properties": props})
    return {"type": "FeatureCollection", "features": feats}


def near(lat: float, lon: float, area_radius_km: float = 0.0, extra_km: float = 0.0) -> List[Dict[str, Any]]:
    """Projects whose effect reaches a point (or an area of ``area_radius_km`` around it).

    ``effect`` (0-1) decays linearly from the footprint edge to its impact radius and is
    scaled by status (built / under construction count more than plans) and expected uplift.
    """
    hits = []
    for p in all_projects():
        d = max(0.0, distance_km(p, lat, lon) - area_radius_km)
        reach = p.get("impact_radius_km", 2) + extra_km
        if d > reach:
            continue
        decay = 1.0 if d == 0 else max(0.0, 1 - d / max(reach, 0.1))
        effect = decay * STATUS_WEIGHT.get(p["status"], 0.5) * UPLIFT_WEIGHT.get(p.get("uplift", "medium"), 0.65)
        s = summary(p)
        s.pop("geometry", None)
        hits.append({**s, "distance_km": round(d, 2), "inside": d == 0, "effect": round(effect, 3)})
    hits.sort(key=lambda h: -h["effect"])
    return hits
