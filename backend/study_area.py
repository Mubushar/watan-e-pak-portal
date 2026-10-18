"""
Case-study report for an area the user draws on the map (circle, rectangle or polygon).

Combines everything the portal knows about the area:

* the portal's own analysis of saved areas (``server.aoi_analyze``): size & valuation of
  listed property, development cost, economic impact, factor scores, 5-year price
  forecast with scenarios, risks and recommendations, related news;
* OpenStreetMap place data (``geo``): every school, mosque, hospital, market, park, bank …
  inside, the nearest essential facility of each kind, the neighbourhoods / sectors inside;
* population (Kontur 2023 estimate) and a development level;
* listings inside (prices, price per marla, mix), housing schemes inside;
* the DHA master plan at the area (plot sizes, roads, facilities) where one is loaded;
* infrastructure mega projects that reach the area (ring roads, motorways, transit, new
  sectors, economic zones …) and how strongly they are likely to move prices;
* province and nearest portal city.

On top it scores the area (amenities, livability, development, market activity, outlook),
grades it, and writes strengths, concerns and a recommendation — rule-based, no AI credit.
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

import geo
import masterplan
import megaprojects
import server as core

ESSENTIALS: List[Tuple[str, str]] = [
    ("education", "School / college"), ("health", "Hospital / clinic"), ("worship", "Mosque"),
    ("shopping", "Market / mall"), ("park", "Park"), ("transport", "Public transport"),
    ("bank", "Bank"), ("fuel", "Fuel station"),
]
NOTABLE_KINDS = ["university", "college", "hospital", "mall", "supermarket", "park", "school"]


def _grade(score: float) -> str:
    return "A" if score >= 80 else "B" if score >= 65 else "C" if score >= 50 else "D" if score >= 35 else "E"


def _band(score: float) -> str:
    return "excellent" if score >= 80 else "good" if score >= 65 else "fair" if score >= 50 else "weak" if score >= 35 else "poor"


def _max_radius_km(center: Tuple[float, float], ring: List[List[float]]) -> float:
    return max((geo.haversine_km(center[0], center[1], p[0], p[1]) for p in ring), default=0.5)


def _province(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    import api  # the province file and point-in-geometry helper live with the endpoints

    for f in api._pk_file("pk_provinces.geojson")["features"]:
        if api._in_geometry(lat, lon, f["geometry"]):
            return {"name": f["properties"]["name"], "name_ur": f["properties"].get("name_ur")}
    return None


def _nearest_city(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    best = None
    for c in core.cities_db:
        if c.latitude is None or c.longitude is None:
            continue
        d = geo.haversine_km(lat, lon, c.latitude, c.longitude)
        if best is None or d < best[0]:
            best = (d, c)
    return {"id": best[1].id, "name": best[1].name, "distance_km": round(best[0], 1)} if best else None


def study(kind: str, *, name: Optional[str] = None, center: Optional[Tuple[float, float]] = None,
          radius_m: Optional[float] = None, bounds: Optional[Dict[str, float]] = None,
          coordinates: Optional[List[List[float]]] = None, save: bool = False) -> Dict[str, Any]:
    """Build the case-study report. ``kind`` is circle | rectangle | polygon."""
    aoi_kind = {"rectangle": "bbox", "circle": "circle", "polygon": "polygon"}.get(kind)
    if not aoi_kind:
        return {"error": "kind must be circle, rectangle or polygon"}
    if aoi_kind == "circle" and (not center or not radius_m):
        return {"error": "A circle needs a centre and a radius"}
    if aoi_kind == "bbox" and not bounds:
        return {"error": "A rectangle needs bounds"}
    if aoi_kind == "polygon" and (not coordinates or len(coordinates) < 3):
        return {"error": "A polygon needs at least 3 corners"}
    if radius_m and radius_m > 25_000:
        return {"error": "Draw a smaller area (up to 25 km across)"}

    city = None
    if center:
        city = _nearest_city(*center)
    elif coordinates:
        city = _nearest_city(sum(p[0] for p in coordinates) / len(coordinates), sum(p[1] for p in coordinates) / len(coordinates))
    elif bounds:
        city = _nearest_city((bounds["south"] + bounds["north"]) / 2, (bounds["west"] + bounds["east"]) / 2)
    city_ref = city["id"] if city and city["distance_km"] <= 60 else None

    created = json.loads(core.aoi_create(
        name=name or "Study area", kind=aoi_kind, description="Drawn on the map for a case study",
        center_latitude=center[0] if center else None, center_longitude=center[1] if center else None,
        radius_m=radius_m, coordinates=coordinates, bounds=bounds, city=city_ref, tags=["study"],
    ))
    if "error" in created:
        return created
    aoi_id = created["id"]
    try:
        base = json.loads(core.aoi_analyze(aoi_id))
        aoi = core._find_aoi(aoi_id)
        ring = [[p[1], p[0]] for p in core._aoi_ring(aoi)]  # GeoJSON [lon, lat] -> [lat, lon]
        lat, lon, _ = core._aoi_center(aoi)
        props = core._aoi_properties(aoi)
    finally:
        if not save:
            core.aois_db[:] = [a for a in core.aois_db if a.id != aoi_id]

    shape = geo.Shape([ring]) if ring else geo.Shape(center=(lat, lon), radius_km=(radius_m or 1000) / 1000)
    area_km2 = max(shape.area_km2, 1e-6)

    # ---- facilities (OpenStreetMap)
    places = geo.places_in(shape) if geo.available() else []
    by_cat = Counter(p["category"] for p in places)
    by_kind = Counter(p["kind"] for p in places)
    notable: Dict[str, List[str]] = {}
    for k in NOTABLE_KINDS:
        names = sorted({p["name"] for p in places if p["kind"] == k})
        if names:
            notable[geo.KIND_LABELS.get(k, k.title())] = names[:6]
    nearest = []
    for cat, label in ESSENTIALS:
        hit = geo.nearest_places(lat, lon, 5.0, category=cat, limit=1) if geo.available() else []
        nearest.append({"category": cat, "label": label, "name": hit[0]["name"] if hit else None,
                        "distance_km": hit[0]["distance_km"] if hit else None, "inside": by_cat.get(cat, 0)})

    # ---- people & development
    population = geo.population_in(shape) if geo.available() else 0
    density = population / area_km2 if population else 0.0
    facilities = sum(by_cat.values())
    development = geo.development_level(density, facilities) if population or facilities else "unknown"
    seen_names: set = set()
    neighbourhoods = []
    for a in sorted((a for a in geo.data().areas if shape.contains(a["center"][0], a["center"][1])) if geo.available() else [],
                    key=lambda a: -(a.get("population") or 0)):
        if a["name"].lower() in seen_names:
            continue
        seen_names.add(a["name"].lower())
        neighbourhoods.append({"name": a["name"], "kind": a.get("kind"), "population": a.get("population")})
        if len(neighbourhoods) >= 12:
            break

    # ---- market (portal listings & schemes)
    sale = [p for p in props if p.price and (p.status or "active") in ("active", "pending")]
    per_marla = sorted(p.price / p.marla_area for p in sale if p.marla_area)
    listings = [{"id": p.id, "title": p.title, "price": p.price, "category": p.category, "marla": p.marla_area,
                 "status": p.status, "latitude": p.latitude, "longitude": p.longitude} for p in props[:12]]
    # Comparables: the nearest listings around the area (within 10 km), for price context
    # when few or none are inside.
    inside_ids = {p.id for p in props}
    comps = []
    for p in core.properties_db:
        if p.id in inside_ids or p.latitude is None or p.longitude is None or not p.price:
            continue
        d = geo.haversine_km(lat, lon, p.latitude, p.longitude)
        if d <= 10:
            comps.append((d, p))
    comps.sort(key=lambda x: x[0])
    comparables = [{"id": p.id, "title": p.title, "price": p.price, "category": p.category, "marla": p.marla_area,
                    "distance_km": round(d, 2), "price_per_marla": round(p.price / p.marla_area) if p.marla_area else None}
                   for d, p in comps[:6]]
    comp_ppm = sorted(c["price_per_marla"] for c in comparables if c["price_per_marla"])
    schemes = [{"id": s.id, "name": s.name, "development_status": s.development_status}
               for s in core.housing_schemes_db
               if s.latitude is not None and s.longitude is not None and shape.contains(s.latitude, s.longitude)]

    # ---- master plan
    plan = None
    if masterplan.available() and masterplan.plans_at(lat, lon):
        r_m = min(1500.0, _max_radius_km((lat, lon), ring) * 1000 if ring else (radius_m or 500))
        plan = masterplan.at(lat, lon, r_m)

    # ---- infrastructure mega projects reaching the area
    area_r = _max_radius_km((lat, lon), ring) if ring else (radius_m or 1000) / 1000
    projects = megaprojects.near(lat, lon, area_radius_km=area_r)
    infra = round(min(100, 25 + 60 * sum(p["effect"] for p in projects))) if projects else 25

    # ---- scores (0-100)
    within = [n for n in nearest if n["distance_km"] is not None and n["distance_km"] <= 1.5]
    amenities = round(100 * len(within) / len(ESSENTIALS))
    per_10k = facilities / max(population / 10_000, 0.3) if population else (facilities * 2.0)
    livability = round(min(100, per_10k * 4))
    dev_score = {"well": 85, "developing": 60, "early": 30}.get(str(development).split()[0].lower(), 50)
    market = round(min(100, 30 + len(props) * 12)) if props else 20
    outlook = round(base.get("forecast", {}).get("composite_index") or base.get("factors", {}).get("index", {}).get("composite") or 50)
    weights = {"amenities": 0.22, "livability": 0.13, "development": 0.18, "market": 0.13, "outlook": 0.22, "infrastructure": 0.12}
    scores = {"amenities": amenities, "livability": livability, "development": dev_score, "market": market, "outlook": outlook,
              "infrastructure": infra}
    overall = round(sum(scores[k] * w for k, w in weights.items()))

    # ---- narrative
    labels = {"amenities": "everyday amenities within 1.5 km", "livability": "facilities per resident",
              "development": "level of development", "market": "listing activity on the portal",
              "outlook": "5-year market outlook", "infrastructure": "pipeline of nearby mega projects"}
    strengths = [f"Strong {labels[k]} ({v}/100)" for k, v in scores.items() if v >= 70]
    concerns = [("Few portal listings here yet, so little local price evidence" if k == "market"
                 else "No major infrastructure project reaches the area" if k == "infrastructure"
                 else f"Weak {labels[k]} ({v}/100)")
                for k, v in scores.items() if v < 40]
    for p in projects[:3]:
        where = "runs through the area" if p["inside"] else f"{p['distance_km']} km away"
        strengths.append(f"{p['name']} ({p['status_label'].lower()}) {where}")
    missing = [n["label"] for n in nearest if n["distance_km"] is None or n["distance_km"] > 3]
    if missing:
        concerns.append("Nothing within 3 km for: " + ", ".join(missing))
    fc = base.get("forecast", {})
    cagr = fc.get("base_cagr")
    if overall >= 70:
        rec = "A well-served, established area — suitable for end-users and steady long-term holding."
    elif overall >= 55:
        rec = "A sound area with some gaps — good value if the missing amenities are close by or planned."
    elif overall >= 40:
        rec = "A developing area — better suited to investors with a longer horizon; verify approvals and possession."
    else:
        rec = "Early-stage or under-served — high risk; check development status, access and legal title carefully."
    big = [p for p in projects if p["status"] in ("under_construction", "approved") and p.get("uplift") == "high"]
    if big:
        rec += f" {big[0]['name']} is a likely price catalyst — prices often move ahead of its completion ({big[0].get('completion', 'TBA')})."
    if cagr is not None:
        rec += f" The portal's base case expects about {cagr * 100:.1f}% a year over {fc.get('horizon_years', 5)} years."

    analysis = base.get("analysis", {})
    return {
        "id": aoi_id if save else None,
        "saved": save,
        "name": name or "Study area",
        "shape": {"kind": kind, "geometry": analysis.get("geometry") or created.get("geometry"),
                  "center": {"latitude": lat, "longitude": lon}, "area_km2": round(area_km2, 3),
                  "area": analysis.get("area")},
        "location": {"province": _province(lat, lon), "nearest_city": city},
        "scores": scores, "weights": weights, "overall": overall, "grade": _grade(overall), "band": _band(overall),
        "summary": {"strengths": strengths, "concerns": concerns, "recommendation": rec},
        "people": {"population": population, "density_per_km2": round(density), "development_level": development,
                   "neighbourhoods": neighbourhoods,
                   "source": "Kontur Population 2023 estimate" if population else None},
        "facilities": {"total": facilities, "by_category": {geo.CATEGORY_LABELS.get(k, k.title()): v for k, v in by_cat.most_common()},
                       "by_kind": {geo.KIND_LABELS.get(k, k.replace('_', ' ').title()): v for k, v in by_kind.most_common(12)},
                       "notable": notable, "nearest": nearest, "source": "OpenStreetMap" if places else None},
        "market": {"listings": len(props), "listings_sample": listings, "price": analysis.get("properties"),
                   "price_per_marla": {"min": round(per_marla[0]) if per_marla else None,
                                       "median": round(per_marla[len(per_marla) // 2]) if per_marla else None,
                                       "max": round(per_marla[-1]) if per_marla else None},
                   "schemes": schemes, "comparables": comparables,
                   "comparable_price_per_marla": comp_ppm[len(comp_ppm) // 2] if comp_ppm else None},
        "master_plan": plan,
        "mega_projects": {"projects": projects, "note": megaprojects.note()},
        "economics": {"development_cost": analysis.get("development_cost"), "economic_impact": analysis.get("economic_impact"),
                      "cost_development": base.get("cost_development")},
        "forecast": fc,
        "factors": base.get("factors"),
        "news": base.get("news", [])[:6],
        "method": "Portal listings & factor model + OpenStreetMap places + Kontur population + DHA master plans + infrastructure mega projects",
    }

