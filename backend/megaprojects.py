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
    return _with_edits(base + extra)


def _edits() -> Dict[str, Dict[str, Any]]:
    import sys

    for name in ("server", "__main__"):
        mod = sys.modules.get(name)
        if mod is not None and hasattr(mod, "megaproject_edits_db"):
            return mod.megaproject_edits_db
    return {}


def _portal_positions() -> Dict[str, Tuple[float, float]]:
    """Inventory projects an admin moved on the map (big projects with an "admin" location)."""
    import sys

    core = sys.modules.get("server") or sys.modules.get("__main__")
    return {b.name.lower(): (b.latitude, b.longitude) for b in getattr(core, "big_projects_db", None) or []
            if getattr(b, "location_precision", None) == "admin" and b.latitude is not None}


def _with_edits(projects: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    edits = _edits()
    moved = _portal_positions()
    out = []
    for p in projects:
        e = edits.get(p["id"])
        if e and e.get("deleted"):
            continue
        if e and e.get("fields"):
            p = {**p, **e["fields"], "edited": True}
        if p.get("portal_project") and p["name"].lower() in moved:
            lat, lon = moved[p["name"].lower()]
            p = {**p, "geometry": {**p["geometry"], "center": [lat, lon]}}
        out.append(p)
    out += [{**e["fields"], "id": k, "created_by_admin": True} for k, e in edits.items() if e.get("created") and not e.get("deleted")]
    return out


def is_shipped(project_id: str) -> bool:
    return any(p["id"] == project_id for p in _load()["projects"])


GEOMETRY_TYPES = ("point", "line", "polygon")
EDITABLE = ("name", "name_ur", "type", "status", "city", "province", "authority", "start_year", "completion",
            "length_km", "summary", "impact", "uplift", "impact_radius_km", "geometry", "sources")


def _in_pk(pt: Any) -> bool:
    return (isinstance(pt, (list, tuple)) and len(pt) == 2 and all(isinstance(x, (int, float)) for x in pt)
            and 23.0 <= pt[0] <= 37.5 and 60.0 <= pt[1] <= 78.0)


def check_fields(f: Dict[str, Any], creating: bool) -> Dict[str, Any]:
    """Validate an admin edit; returns the cleaned fields (raises ValueError with a plain message)."""
    out = {k: v for k, v in f.items() if k in EDITABLE}
    if creating or "name" in out:
        if not str(out.get("name") or "").strip():
            raise ValueError("A name is required")
        out["name"] = str(out["name"]).strip()[:160]
    if "type" in out and out["type"] not in TYPE_LABELS:
        raise ValueError(f"type must be one of: {', '.join(TYPE_LABELS)}")
    if "status" in out and out["status"] not in STATUS_LABELS:
        raise ValueError(f"status must be one of: {', '.join(STATUS_LABELS)}")
    if "uplift" in out and out["uplift"] not in UPLIFT_WEIGHT:
        raise ValueError("uplift must be high, medium or low")
    if "impact_radius_km" in out:
        r = out["impact_radius_km"]
        if not isinstance(r, (int, float)) or not 0 < r <= 50:
            raise ValueError("impact radius must be between 0 and 50 km")
    if creating or "geometry" in out:
        g = out.get("geometry") or {}
        t = g.get("type")
        if t not in GEOMETRY_TYPES:
            raise ValueError("geometry type must be point, line or polygon")
        if t == "point":
            if not _in_pk(g.get("center")):
                raise ValueError("The point must be inside Pakistan")
            g = {"type": "point", "center": [round(g["center"][0], 6), round(g["center"][1], 6)],
                 "radius_km": float(g.get("radius_km") or 0.3)}
        else:
            key = "path" if t == "line" else "ring"
            pts = g.get(key) or []
            need = 2 if t == "line" else 3
            if len(pts) < need or not all(_in_pk(x) for x in pts):
                raise ValueError(f"A {t} needs at least {need} points inside Pakistan")
            if len(pts) > 2000:
                raise ValueError("Too many points (2000 at most)")
            g = {"type": t, key: [[round(x[0], 6), round(x[1], 6)] for x in pts]}
        out["geometry"] = g
    if creating:
        out.setdefault("type", "cbd")
        out.setdefault("status", "planned")
        out.setdefault("uplift", "medium")
        out.setdefault("impact_radius_km", 2)
        out.setdefault("summary", "")
        out.setdefault("impact", "")
        out.setdefault("city", "")
        out.setdefault("province", "")
        out.setdefault("sources", [])
    return out


def admin_save(project_id: Optional[str], fields: Dict[str, Any]) -> Dict[str, Any]:
    """Create (project_id None) or change a mega project; returns the project as listed."""
    import re
    from datetime import datetime

    edits = _edits()
    now = datetime.now().isoformat(timespec="seconds")
    if project_id is None:
        clean = check_fields(fields, creating=True)
        base = re.sub(r"[^a-z0-9]+", "-", clean["name"].lower()).strip("-")[:48] or "project"
        new_id, n = f"admin-{base}", 2
        while any(p["id"] == new_id for p in all_projects()) or new_id in edits:
            new_id, n = f"admin-{base}-{n}", n + 1
        edits[new_id] = {"created": True, "deleted": False, "fields": clean, "updated_at": now}
        return summary(next(p for p in all_projects() if p["id"] == new_id))
    current = get(project_id)
    if current is None:
        raise KeyError(project_id)
    if current.get("portal_project"):
        raise ValueError("This is a portal project — edit it as a big project (its units follow it)")
    clean = check_fields(fields, creating=False)
    e = edits.setdefault(project_id, {"created": False, "deleted": False, "fields": {}})
    e["fields"] = {**e.get("fields", {}), **clean}
    e["updated_at"] = now
    return summary(get(project_id))


def admin_add_photo(project_id: str, url: str, primary: bool = False) -> Dict[str, Any]:
    """A photo taken on site: kept with the project's admin edits; the first one becomes its picture."""
    from datetime import datetime

    current = get(project_id)
    if current is None:
        raise KeyError(project_id)
    if current.get("portal_project"):
        raise ValueError("This is a portal project — add photos to it as a big project")
    edits = _edits()
    e = edits.setdefault(project_id, {"created": False, "deleted": False, "fields": {}})
    fields = e.setdefault("fields", {})
    images = [*(fields.get("images") or []), url]
    fields["images"] = images
    if primary or not any(u.startswith("/media/") for u in images[:-1]):
        fields["image"], fields["image_credit"] = url, "Photo taken on site (Arz-e-Pak survey)"
    e["updated_at"] = datetime.now().isoformat(timespec="seconds")
    return summary(get(project_id))


def admin_delete(project_id: str) -> Dict[str, Any]:
    edits = _edits()
    current = get(project_id)
    if current is None:
        raise KeyError(project_id)
    if current.get("portal_project"):
        raise ValueError("This is a portal project — delete it as a big project")
    if project_id in edits and edits[project_id].get("created"):
        edits.pop(project_id)
    else:
        edits[project_id] = {**edits.get(project_id, {"fields": {}}), "deleted": True}
    return {"deleted": True, "id": project_id}


def admin_reset(project_id: str) -> Dict[str, Any]:
    """Drop the admin's changes to a shipped project (back to the data file)."""
    edits = _edits()
    if not is_shipped(project_id):
        raise KeyError(project_id)
    edits.pop(project_id, None)
    return summary(get(project_id))


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
