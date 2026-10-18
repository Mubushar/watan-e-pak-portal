"""
Build Pakistan's district boundaries for the portal map from OpenStreetMap.

Source: the same Geofabrik extract as the roads (media/osm/pakistan-latest.osm.pbf,
© OpenStreetMap contributors, ODbL) — administrative boundaries at admin_level 6
(districts), which OpenStreetMap keeps current, including recently created districts.
Boundaries of neighbouring countries in the extract are dropped by checking each district's
centre against the province file (geodata/pk_provinces.geojson).

Output: ``media/boundaries/pk_districts.geojson`` (git-ignored; served by ``GET /geo/districts``),
simplified to about 150 m, with English / Urdu names, province, area and a label point.

    uv run --no-project --python 3.12 --with osmium python build_districts.py
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import osmium

from build_roads import SRC, _dp
from build_water import _area_km2

HERE = Path(__file__).parent
OUT = HERE / "media" / "boundaries" / "pk_districts.geojson"
PROVINCES = HERE / "geodata" / "pk_provinces.geojson"
TOLERANCE = 0.0015


def _in_ring(lat: float, lon: float, ring: list) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _province_of(lat: float, lon: float, provinces: list) -> str | None:
    for name, polys in provinces:
        for poly in polys:
            if _in_ring(lat, lon, poly[0]):
                return name
    return None


class Districts(osmium.SimpleHandler):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list = []

    def area(self, a) -> None:  # noqa: ANN001
        t = a.tags
        if t.get("boundary") != "administrative" or t.get("admin_level") != "6" or a.from_way():
            return
        rings = []
        for outer in a.outer_rings():
            pts = [[round(n.lat, 5), round(n.lon, 5)] for n in outer if n.location.valid()]
            if len(pts) >= 4:
                rings.append(pts)
        if not rings:
            return
        self.rows.append({
            "name": t.get("name:en") or t.get("name"),
            "name_ur": t.get("name:ur"),
            "osm_id": a.orig_id(),
            "rings": rings,
        })


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else SRC
    if not src.exists():
        print(f"Missing {src}. Download it first (see build_roads.py).")
        return 1
    t0 = time.time()
    prov = json.loads(PROVINCES.read_text(encoding="utf-8"))
    provinces = []
    for f in prov["features"]:
        g = f["geometry"]
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        provinces.append((f["properties"]["name"], polys))

    h = Districts()
    h.apply_file(str(src), locations=True, idx="flex_mem")
    feats, dropped = [], 0
    for d in h.rows:
        big = max(d["rings"], key=_area_km2)
        lat = sum(p[0] for p in big) / len(big)
        lon = sum(p[1] for p in big) / len(big)
        province = _province_of(lat, lon, provinces)
        if not province or not d["name"]:
            dropped += 1
            continue
        area = sum(_area_km2(r) for r in d["rings"])
        polys = []
        for r in d["rings"]:
            s = _dp(r, TOLERANCE)
            if len(s) >= 4:
                ring = [[p[1], p[0]] for p in s]
                if ring[0] != ring[-1]:
                    ring.append(ring[0])
                polys.append([ring])
        if not polys:
            continue
        feats.append({
            "type": "Feature",
            "geometry": {"type": "MultiPolygon", "coordinates": polys},
            "properties": {"name": d["name"], "name_ur": d["name_ur"], "province": province,
                           "area_km2": round(area, 1), "label": [round(lat, 4), round(lon, 4)], "osm_id": d["osm_id"]},
        })
    feats.sort(key=lambda f: (f["properties"]["province"], f["properties"]["name"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out = {
        "type": "FeatureCollection",
        "meta": {
            "source": "OpenStreetMap via Geofabrik (boundary=administrative, admin_level=6)",
            "attribution": "© OpenStreetMap contributors (ODbL)",
            "extract_date": datetime.fromtimestamp(src.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d"),
            "built": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        },
        "features": feats,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    by_prov: dict = {}
    for f in feats:
        by_prov[f["properties"]["province"]] = by_prov.get(f["properties"]["province"], 0) + 1
    print(f"{len(feats)} districts ({dropped} outside Pakistan dropped) -> {OUT} ({OUT.stat().st_size / 1e6:.1f} MB) in {time.time() - t0:.0f}s")
    print(by_prov)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
