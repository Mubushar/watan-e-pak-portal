"""
Build the offline geodata the assistant answers from:

* places.json.gz      named places (schools, malls, hospitals, mosques, parks …)  — OpenStreetMap
* areas.json.gz       neighbourhoods, sectors, phases, housing societies + their
                      estimated population                                     — OpenStreetMap, Nominatim, Kontur
* population.json.gz  population per ~0.74 km² hexagon for each metro           — Kontur Population

Run from backend/ (takes a few minutes; Overpass is slow)::

    uv run python geodata/build_geodata.py --kontur PATH/kontur_population_PK_20231101.gpkg

The Kontur file is the free "Pakistan: Population Density for 400m H3 Hexagons"
download from data.humdata.org (CC BY 4.0, ~27 MB gzipped).

Data © OpenStreetMap contributors (ODbL 1.0); population © Kontur (CC BY 4.0).
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import sqlite3
import struct
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import httpx

HERE = Path(__file__).resolve().parent
UA = {"User-Agent": "Arz-e-Pak-geodata-builder/1.0 (real-estate portal; offline import)"}
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://maps.mail.ru/osm/tools/overpass/api/interpreter"]

# Metro regions: (south, west, north, east)
REGIONS: Dict[str, Dict[str, Any]] = {
    "islamabad_rawalpindi": {"label": "Islamabad / Rawalpindi", "bbox": (33.40, 72.80, 33.85, 73.35)},
    "lahore": {"label": "Lahore", "bbox": (31.25, 74.05, 31.75, 74.60)},
    "karachi": {"label": "Karachi", "bbox": (24.75, 66.85, 25.20, 67.45)},
}

# Well-known housing societies, looked up on Nominatim for a proper outline.
SOCIETIES: Dict[str, List[str]] = {
    "islamabad_rawalpindi": [
        *[f"Bahria Town Phase {n}, Rawalpindi" for n in range(1, 9)],
        "Bahria Enclave, Islamabad", "Bahria Garden City, Islamabad",
        *[f"DHA Phase {n}, Islamabad" for n in range(1, 6)],
        "DHA Valley, Islamabad", "Gulberg Greens, Islamabad", "Gulberg Residencia, Islamabad",
        "B-17, Islamabad", "G-13, Islamabad", "G-11, Islamabad", "F-11, Islamabad", "E-11, Islamabad",
        "I-8, Islamabad", "G-9, Islamabad", "F-7, Islamabad", "F-6, Islamabad", "F-10, Islamabad",
        "PWD Housing Scheme, Islamabad", "Soan Garden, Islamabad", "Naval Anchorage, Islamabad",
        "Satellite Town, Rawalpindi", "Westridge, Rawalpindi", "Chaklala Scheme 3, Rawalpindi",
        "Saddar, Rawalpindi", "Gulraiz Housing Scheme, Rawalpindi", "Adiala Road, Rawalpindi",
    ],
    "lahore": [
        *[f"DHA Phase {n}, Lahore" for n in range(1, 10)],
        "Bahria Town, Lahore", "Johar Town, Lahore", "Gulberg, Lahore", "Model Town, Lahore",
        "Wapda Town, Lahore", "Valencia Town, Lahore", "Lake City, Lahore", "Allama Iqbal Town, Lahore",
        "Garden Town, Lahore", "Cantt, Lahore", "Askari 10, Lahore", "Paragon City, Lahore",
        "LDA Avenue 1, Lahore", "State Life Housing Society, Lahore", "Faisal Town, Lahore",
    ],
    "karachi": [
        *[f"DHA Phase {n}, Karachi" for n in range(1, 9)],
        "Clifton, Karachi", "Gulshan-e-Iqbal, Karachi", "Gulistan-e-Jauhar, Karachi",
        "North Nazimabad, Karachi", "PECHS, Karachi", "Bahria Town Karachi", "Scheme 33, Karachi",
        "Naya Nazimabad, Karachi", "Saddar, Karachi", "Malir Cantonment, Karachi",
    ],
}


# ------------------------------------------------------------------ helpers

def overpass(query: str, label: str) -> List[Dict[str, Any]]:
    for attempt in range(3):
        for url in OVERPASS:
            t = time.time()
            try:
                r = httpx.post(url, data={"data": query}, timeout=300, headers=UA)
                if r.headers.get("content-type", "").startswith("application/json"):
                    els = r.json().get("elements", [])
                    print(f"  {label}: {len(els)} elements ({time.time() - t:.0f}s)")
                    return els
                print(f"  {label}: {url.split('/')[2]} answered {r.status_code}, retrying")
            except httpx.HTTPError as exc:
                print(f"  {label}: {url.split('/')[2]} {type(exc).__name__}, retrying")
        time.sleep(20 * (attempt + 1))
    raise SystemExit(f"Overpass failed for {label}")


def haversine_km(a: float, b: float, c: float, d: float) -> float:
    p1, p2 = math.radians(a), math.radians(c)
    dp, dl = p2 - p1, math.radians(d - b)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(h))


def polygon_area_km2(ring: List[List[float]]) -> float:
    """Approximate area of a [[lat, lon], …] ring (equirectangular, fine at city scale)."""
    if len(ring) < 3:
        return 0.0
    lat0 = math.radians(sum(p[0] for p in ring) / len(ring))
    xy = [(math.radians(p[1]) * math.cos(lat0) * 6371.0088, math.radians(p[0]) * 6371.0088) for p in ring]
    s = 0.0
    for (x1, y1), (x2, y2) in zip(xy, xy[1:] + xy[:1]):
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def point_in_ring(lat: float, lon: float, ring: List[List[float]]) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        yi, xi = ring[i]
        yj, xj = ring[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def simplify(ring: List[List[float]], max_points: int = 48) -> List[List[float]]:
    if len(ring) > 1 and ring[0] == ring[-1]:
        ring = ring[:-1]
    if len(ring) <= max_points:
        return [[round(a, 5), round(b, 5)] for a, b in ring]
    step = len(ring) / max_points
    return [[round(ring[int(i * step)][0], 5), round(ring[int(i * step)][1], 5)] for i in range(max_points)]


def bbox_ring(s: float, w: float, n: float, e: float) -> List[List[float]]:
    return [[s, w], [s, e], [n, e], [n, w]]


def in_bbox(lat: float, lon: float, bb: Tuple[float, float, float, float]) -> bool:
    return bb[0] <= lat <= bb[2] and bb[1] <= lon <= bb[3]


# ------------------------------------------------------------------ places

def classify(t: Dict[str, str]) -> Optional[Tuple[str, str]]:
    a, s, l = t.get("amenity"), t.get("shop"), t.get("leisure")
    name = (t.get("name") or "").lower()
    if a in ("school", "kindergarten"):
        return "education", a
    if a in ("college", "university"):
        return "education", a
    if a == "hospital":
        return "health", "hospital"
    if a in ("clinic", "doctors", "dentist"):
        return "health", "clinic"
    if a == "pharmacy":
        return "health", "pharmacy"
    if a == "place_of_worship":
        muslim = t.get("religion") == "muslim" or any(w in name for w in ("masjid", "mosque", "jamia", "مسجد"))
        return "worship", "mosque" if muslim else (t.get("religion") or "place_of_worship")
    if s == "mall":
        return "shopping", "mall"
    if s in ("supermarket", "department_store"):
        return "shopping", "supermarket"
    if a == "marketplace":
        return "shopping", "market"
    if l == "park":
        return "park", "park"
    if l in ("sports_centre", "stadium"):
        return "park", "sports"
    if a == "bank":
        return "bank", "bank"
    if a in ("restaurant", "cafe", "fast_food"):
        return "restaurant", a
    if a == "bus_station" or t.get("railway") == "station":
        return "transport", "station"
    if a == "fuel":
        return "fuel", "fuel"
    if a in ("police", "townhall", "courthouse", "post_office"):
        return "government", a
    return None


def build_places(region: str, bb: Tuple[float, float, float, float]) -> List[List[Any]]:
    b = ",".join(str(x) for x in bb)
    q = f"""[out:json][timeout:280];
(
 nwr["name"]["amenity"~"^(school|kindergarten|college|university|hospital|clinic|doctors|dentist|pharmacy|place_of_worship|marketplace|bank|restaurant|cafe|fast_food|bus_station|fuel|police|townhall|courthouse|post_office)$"]({b});
 nwr["name"]["shop"~"^(mall|supermarket|department_store)$"]({b});
 nwr["name"]["leisure"~"^(park|sports_centre|stadium)$"]({b});
 nwr["name"]["railway"="station"]({b});
);
out center tags;"""
    rows, seen = [], set()
    for e in overpass(q, f"{region} places"):
        t = e.get("tags") or {}
        c = classify(t)
        lat = e.get("lat") or (e.get("center") or {}).get("lat")
        lon = e.get("lon") or (e.get("center") or {}).get("lon")
        if not c or lat is None:
            continue
        name = (t.get("name:en") or t.get("name") or "").strip()
        key = (name.lower(), c[1], round(lat, 3), round(lon, 3))
        if not name or key in seen:
            continue
        seen.add(key)
        # [name, urdu name, category, kind, lat, lon]
        rows.append([name, t.get("name:ur") or "", c[0], c[1], round(lat, 5), round(lon, 5)])
    return rows


# ------------------------------------------------------------------ areas

PLACE_RADIUS_M = {"suburb": 1500, "neighbourhood": 600, "quarter": 500}


def build_areas(region: str, bb: Tuple[float, float, float, float]) -> List[Dict[str, Any]]:
    b = ",".join(str(x) for x in bb)
    q = f"""[out:json][timeout:280];
(
 node["place"~"^(suburb|neighbourhood|quarter)$"]["name"]({b});
 way["place"~"^(suburb|neighbourhood|quarter)$"]["name"]({b});
 way["landuse"="residential"]["name"]({b});
 relation["place"~"^(suburb|neighbourhood|quarter)$"]["name"]({b});
 relation["landuse"="residential"]["name"]({b});
 relation["boundary"="administrative"]["admin_level"~"^(8|9|10)$"]["name"]({b});
);
out geom;"""
    areas: Dict[str, Dict[str, Any]] = {}
    for e in overpass(q, f"{region} areas"):
        t = e.get("tags") or {}
        name = (t.get("name:en") or t.get("name") or "").strip()
        if not name:
            continue
        kind = t.get("place") or ("residential" if t.get("landuse") == "residential" else "admin")
        if e["type"] == "node":
            ring, center = [], [e["lat"], e["lon"]]
            radius = PLACE_RADIUS_M.get(kind, 600)
        elif e["type"] == "way" and e.get("geometry"):
            ring = simplify([[p["lat"], p["lon"]] for p in e["geometry"]])
            if len(ring) < 3:
                continue
            center = [sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring)]
            radius = None
        elif e.get("bounds"):
            g = e["bounds"]
            ring = bbox_ring(g["minlat"], g["minlon"], g["maxlat"], g["maxlon"])
            center = [(g["minlat"] + g["maxlat"]) / 2, (g["minlon"] + g["maxlon"]) / 2]
            radius = None
        else:
            continue
        if not in_bbox(center[0], center[1], bb):
            continue
        area_km2 = polygon_area_km2(ring) if ring else math.pi * (radius / 1000) ** 2
        if ring and area_km2 < 0.005:  # a single compound / building block
            continue
        key = f"{name.lower()}|{round(center[0], 3)}|{round(center[1], 3)}"
        areas[key] = {"name": name, "name_ur": t.get("name:ur") or "", "kind": kind, "source": "osm",
                      "center": [round(center[0], 5), round(center[1], 5)], "ring": ring,
                      "radius_m": radius, "area_km2": round(area_km2, 3)}
    return list(areas.values())


def nominatim_societies(region: str, bb: Tuple[float, float, float, float]) -> List[Dict[str, Any]]:
    out = []
    for q in SOCIETIES.get(region, []):
        time.sleep(1.1)  # Nominatim usage policy: at most 1 request per second
        try:
            r = httpx.get("https://nominatim.openstreetmap.org/search", headers=UA, timeout=30, params={
                "q": q, "format": "jsonv2", "countrycodes": "pk", "limit": 1, "polygon_geojson": 1,
                "polygon_threshold": 0.0002})
            hits = r.json()
        except (httpx.HTTPError, ValueError):
            continue
        if not hits:
            print(f"    not found: {q}")
            continue
        h = hits[0]
        lat, lon = float(h["lat"]), float(h["lon"])
        if not in_bbox(lat, lon, bb):
            continue
        geo = h.get("geojson") or {}
        ring: List[List[float]] = []
        if geo.get("type") == "Polygon":
            ring = simplify([[c[1], c[0]] for c in geo["coordinates"][0]], 64)
        elif geo.get("type") == "MultiPolygon":
            biggest = max(geo["coordinates"], key=lambda p: len(p[0]))
            ring = simplify([[c[1], c[0]] for c in biggest[0]], 64)
        if not ring:
            s, n, w, e = (float(x) for x in h["boundingbox"])
            ring = bbox_ring(s, w, n, e) if (n - s) * (e - w) > 1e-6 else []
        label = q.split(",")[0].strip()
        out.append({"name": label, "name_ur": "", "kind": "society", "source": "nominatim",
                    "osm_name": h.get("display_name", "")[:120],
                    "center": [round(lat, 5), round(lon, 5)], "ring": ring,
                    "radius_m": None if ring else 1500,
                    "area_km2": round(polygon_area_km2(ring), 3) if ring else round(math.pi * 1.5 ** 2, 3)})
        print(f"    {label}: {'outline' if ring else 'point'}")
    return out


# ------------------------------------------------------------------ population (Kontur H3 grid)

def mercator_to_latlon(x: float, y: float) -> Tuple[float, float]:
    lon = x / 6378137.0 * 180.0 / math.pi
    lat = (2 * math.atan(math.exp(y / 6378137.0)) - math.pi / 2) * 180.0 / math.pi
    return lat, lon


def gpkg_envelope_center(blob: bytes) -> Optional[Tuple[float, float]]:
    """Centre of a GeoPackage geometry's envelope (header: 'GP', version, flags, srs id, envelope)."""
    if blob[:2] != b"GP":
        return None
    flags = blob[3]
    env = (flags >> 1) & 0b111
    if env == 0:
        return None
    endian = "<" if flags & 1 else ">"
    minx, maxx, miny, maxy = struct.unpack(endian + "4d", blob[8:40])
    return (minx + maxx) / 2, (miny + maxy) / 2


def build_population(gpkg: Path) -> Dict[str, List[List[float]]]:
    con = sqlite3.connect(f"file:{gpkg}?mode=ro", uri=True)
    cells: Dict[str, List[List[float]]] = {r: [] for r in REGIONS}
    for blob, pop in con.execute("select geom, population from population"):
        c = gpkg_envelope_center(blob)
        if not c or not pop:
            continue
        lat, lon = mercator_to_latlon(*c)
        for region, meta in REGIONS.items():
            if in_bbox(lat, lon, meta["bbox"]):
                cells[region].append([round(lat, 5), round(lon, 5), int(round(pop))])
                break
    for region, rows in cells.items():
        print(f"  {region}: {len(rows)} population cells, {sum(r[2] for r in rows):,} people")
    return cells


HEX_KM2 = 0.737  # average H3 resolution-8 cell area


def population_of(area: Dict[str, Any], cells: List[List[float]]) -> int:
    lat, lon = area["center"]
    if area["ring"]:
        ring = area["ring"]
        s, n = min(p[0] for p in ring), max(p[0] for p in ring)
        w, e = min(p[1] for p in ring), max(p[1] for p in ring)
        inside = [c for c in cells if s <= c[0] <= n and w <= c[1] <= e and point_in_ring(c[0], c[1], ring)]
    else:
        r_km = (area["radius_m"] or 600) / 1000.0
        inside = [c for c in cells if haversine_km(lat, lon, c[0], c[1]) <= r_km]
    if len(inside) >= 3:
        return int(sum(c[2] for c in inside))
    # Small area: local density (cells within ~700 m) × its size.
    near = [c for c in cells if haversine_km(lat, lon, c[0], c[1]) <= 0.7] or inside
    if not near:
        return 0
    density = sum(c[2] for c in near) / (len(near) * HEX_KM2)
    return int(density * area["area_km2"])


def add_parents(areas: List[Dict[str, Any]]) -> None:
    """Name the bigger areas each area sits in (e.g. a sector inside a phase)."""
    boxes = []
    for a in areas:
        if a["ring"]:
            r = a["ring"]
            boxes.append((min(p[0] for p in r), min(p[1] for p in r), max(p[0] for p in r), max(p[1] for p in r)))
        else:
            boxes.append(None)
    for a in areas:
        lat, lon = a["center"]
        parents = []
        for b, box in zip(areas, boxes):
            if b is a or box is None or b["area_km2"] <= a["area_km2"] * 1.5:
                continue
            if box[0] <= lat <= box[2] and box[1] <= lon <= box[3] and point_in_ring(lat, lon, b["ring"]):
                parents.append((b["area_km2"], b["name"]))
        a["parents"] = [n for _, n in sorted(parents)][:3]


# ------------------------------------------------------------------ main

def write(name: str, data: Any) -> None:
    path = HERE / name
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {path.name}: {path.stat().st_size / 1024:.0f} KB")


def main(argv: Optional[Iterable[str]] = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kontur", required=True, type=Path, help="kontur_population_PK_*.gpkg (unzipped)")
    ap.add_argument("--regions", default=",".join(REGIONS), help="comma-separated subset of " + ", ".join(REGIONS))
    args = ap.parse_args(list(argv) if argv is not None else None)
    regions = [r for r in args.regions.split(",") if r in REGIONS]

    print("population grid…")
    cells = build_population(args.kontur)
    places: Dict[str, List[List[Any]]] = {}
    areas: Dict[str, List[Dict[str, Any]]] = {}
    for region in regions:
        bb = REGIONS[region]["bbox"]
        print(f"{REGIONS[region]['label']}:")
        places[region] = build_places(region, bb)
        found = build_areas(region, bb)
        print("  housing societies (Nominatim)…")
        found += nominatim_societies(region, bb)
        add_parents(found)
        for a in found:
            a["population"] = population_of(a, cells[region])
        areas[region] = found
        print(f"  {len(places[region])} places, {len(found)} areas")

    meta = {"built": time.strftime("%Y-%m-%d"), "regions": {r: REGIONS[r] for r in regions},
            "attribution": "Places and areas © OpenStreetMap contributors (ODbL); population © Kontur Population 2023 (CC BY 4.0)"}
    write("places.json.gz", {"meta": meta, "fields": ["name", "name_ur", "category", "kind", "lat", "lon"], "regions": places})
    write("areas.json.gz", {"meta": meta, "regions": areas})
    write("population.json.gz", {"meta": meta, "cell_km2": HEX_KM2, "fields": ["lat", "lon", "population"],
                                 "regions": {r: cells[r] for r in regions}})


if __name__ == "__main__":
    sys.exit(main())
