"""
Location registry checks: find listings, big projects and mega-project points whose location is
missing or looks wrong, so an admin can fix them on the map (Locate tool).

A location "looks wrong" when it is
  • outside Pakistan,
  • more than CITY_KM from the centre of the record's city,
  • more than SOCIETY_KM from the centre of its housing society, or
  • within 60 m of its city's centre — usually a city-level geocode, not the real spot.
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional

CITY_KM = 40.0
SOCIETY_KM = 8.0
CENTROID_M = 60.0


def _core() -> Any:
    return sys.modules.get("server") or sys.modules.get("__main__")


def _in_pk(lat: float, lon: float) -> bool:
    return 23.0 <= lat <= 37.5 and 60.0 <= lon <= 78.0


def check(lat: Optional[float], lon: Optional[float], city: Any = None, scheme: Any = None) -> Dict[str, Any]:
    """Status of one location: ok | missing | suspect (with the reason)."""
    core = _core()
    if lat is None or lon is None:
        return {"status": "missing", "issue": "No location yet"}
    if not _in_pk(lat, lon):
        return {"status": "suspect", "issue": "Outside Pakistan"}
    if scheme is not None and scheme.latitude is not None and scheme.longitude is not None:
        d = core.haversine_km(lat, lon, scheme.latitude, scheme.longitude)
        if d > SOCIETY_KM:
            return {"status": "suspect", "issue": f"{d:.1f} km from {scheme.name}", "distance_km": round(d, 1)}
    if city is not None and city.latitude is not None and city.longitude is not None:
        d = core.haversine_km(lat, lon, city.latitude, city.longitude)
        if d > CITY_KM:
            return {"status": "suspect", "issue": f"{d:.0f} km from {city.name}", "distance_km": round(d, 1)}
        if d * 1000 <= CENTROID_M:
            return {"status": "suspect", "issue": f"On {city.name}'s centre point — probably not the real spot"}
    return {"status": "ok", "issue": None}


def search(kind: str = "property", q: str = "", status: str = "problems", page: int = 1, page_size: int = 30) -> Dict[str, Any]:
    """Records of one kind with their location status. ``status``: problems (missing + suspect) |
    missing | suspect | ok | all."""
    import megaprojects

    core = _core()
    cities = {c.id: c for c in core.cities_db}
    by_name = {c.name.lower(): c for c in core.cities_db}
    schemes = {s.id: s for s in core.housing_schemes_db}
    needle = (q or "").strip().lower()
    rows: List[Dict[str, Any]] = []

    def society(sid: Optional[str]) -> Optional[Dict[str, Any]]:
        s = schemes.get(sid) if sid else None
        return {"id": s.id, "name": s.name, "latitude": s.latitude, "longitude": s.longitude} if s else None

    if kind == "property":
        for p in core.properties_db:
            if p.project_id:  # unit listings follow their project
                continue
            c, s = cities.get(p.city_id), schemes.get(p.scheme_id) if p.scheme_id else None
            text = f"{p.title} {p.street_address or ''} {p.plot_number or ''} {c.name if c else ''} {s.name if s else ''} {p.id}".lower()
            if needle and needle not in text:
                continue
            rows.append({"kind": "property", "id": p.id, "name": p.title, "subtitle": ", ".join(x for x in [s.name if s else None, c.name if c else None] if x),
                         "city": c.name if c else None, "city_center": [c.latitude, c.longitude] if c and c.latitude is not None else None,
                         "society": society(p.scheme_id), "latitude": p.latitude, "longitude": p.longitude, "listing_status": p.status,
                         **check(p.latitude, p.longitude, c, s)})
    elif kind == "project":
        for b in core.big_projects_db:
            c, s = cities.get(b.city_id), schemes.get(b.scheme_id) if b.scheme_id else None
            if needle and needle not in f"{b.name} {b.address or ''} {c.name if c else ''} {b.id}".lower():
                continue
            rows.append({"kind": "project", "id": b.id, "name": b.name, "subtitle": ", ".join(x for x in [s.name if s else None, c.name if c else None] if x),
                         "city": c.name if c else None, "city_center": [c.latitude, c.longitude] if c and c.latitude is not None else None,
                         "society": society(b.scheme_id), "latitude": b.latitude, "longitude": b.longitude, **check(b.latitude, b.longitude, c, s)})
    elif kind == "mega":
        for m in megaprojects.all_projects():
            if m.get("portal_project") or m["geometry"]["type"] != "point":
                continue
            if needle and needle not in f"{m['name']} {m.get('city', '')} {m['id']}".lower():
                continue
            c = by_name.get((m.get("city") or "").lower())
            lat, lon = m["geometry"]["center"]
            rows.append({"kind": "mega", "id": m["id"], "name": m["name"], "subtitle": m.get("city") or "",
                         "city": m.get("city"), "city_center": [c.latitude, c.longitude] if c and c.latitude is not None else None,
                         "society": None, "latitude": lat, "longitude": lon, "radius_km": m["geometry"].get("radius_km"),
                         **check(lat, lon, c)})
    else:
        raise ValueError("kind must be property, project or mega")

    counts = {k: sum(1 for r in rows if r["status"] == k) for k in ("missing", "suspect", "ok")}
    wanted = {"problems": ("missing", "suspect"), "missing": ("missing",), "suspect": ("suspect",), "ok": ("ok",)}.get(status)
    if wanted:
        rows = [r for r in rows if r["status"] in wanted]
    rows.sort(key=lambda r: ({"missing": 0, "suspect": 1, "ok": 2}[r["status"]], r["name"].lower()))
    page_size = max(1, min(page_size, 100))
    pages = max(1, -(-len(rows) // page_size))
    page = max(1, min(page, pages))
    return {"kind": kind, "total": len(rows), "page": page, "pages": pages, "counts": counts,
            "results": rows[(page - 1) * page_size: page * page_size]}
