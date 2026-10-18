"""
Build Pakistan's water bodies for the portal map from OpenStreetMap.

Source: the same Geofabrik extract as the roads (media/osm/pakistan-latest.osm.pbf,
© OpenStreetMap contributors, ODbL). Keeps:

* rivers and canals (lines), with English / Urdu names;
* lakes, reservoirs / dams, river beds, ponds and basins (areas, from closed ways and
  multipolygons), with their size in km² — tiny ponds under 0.01 km² are dropped.

Every feature is simplified for four zoom bands. Output: ``media/water/pk_water.json``
(git-ignored; served by ``water.py`` / ``GET /geo/water``).

    uv run --no-project --python 3.12 --with osmium python build_water.py
"""

from __future__ import annotations

import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import osmium

from build_roads import SRC, TOLERANCES, _dp

OUT = Path(__file__).parent / "media" / "water" / "pk_water.json"
LINES = {"river": "river", "canal": "canal"}
MIN_AREA_KM2 = 0.01


def _area_km2(ring: list) -> float:
    lat0 = math.radians(sum(p[0] for p in ring) / len(ring))
    kx, ky = 111.32 * math.cos(lat0), 110.57
    a = 0.0
    for i in range(len(ring)):
        y1, x1 = ring[i]
        y2, x2 = ring[(i + 1) % len(ring)]
        a += x1 * kx * y2 * ky - x2 * kx * y1 * ky
    return abs(a) / 2


def _area_class(tags) -> str | None:  # noqa: ANN001
    natural, water, landuse = tags.get("natural"), tags.get("water"), tags.get("landuse")
    if natural == "water" or landuse in ("reservoir", "basin") or tags.get("waterway") == "riverbank":
        if water in ("river", "canal", "stream", "oxbow") or tags.get("waterway") == "riverbank":
            return "riverbed"
        if water in ("reservoir",) or landuse == "reservoir":
            return "reservoir"
        if water in ("pond", "basin", "wastewater", "fishpond") or landuse == "basin":
            return "pond"
        return "lake"
    return None


def _names(tags, row: dict) -> None:  # noqa: ANN001
    n = tags.get("name:en") or tags.get("name")
    u = tags.get("name:ur")
    if n:
        row["n"] = n
    if u:
        row["u"] = u


class Water(osmium.SimpleHandler):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list = []

    def way(self, w) -> None:  # noqa: ANN001
        c = LINES.get(w.tags.get("waterway", ""))
        if not c:
            return
        pts = [[round(n.location.lat, 5), round(n.location.lon, 5)] for n in w.nodes if n.location.valid()]
        if len(pts) < 2:
            return
        lats, lons = [p[0] for p in pts], [p[1] for p in pts]
        row = {"c": c, "b": [min(lats), min(lons), max(lats), max(lons)], "p": [_dp(pts, t) for t in TOLERANCES]}
        _names(w.tags, row)
        self.rows.append(row)

    def area(self, a) -> None:  # noqa: ANN001
        c = _area_class(a.tags)
        if not c:
            return
        for outer in a.outer_rings():
            pts = [[round(n.lat, 5), round(n.lon, 5)] for n in outer if n.location.valid()]
            if len(pts) < 4:
                continue
            km2 = _area_km2(pts)
            if km2 < MIN_AREA_KM2:
                continue
            lats, lons = [p[0] for p in pts], [p[1] for p in pts]
            bands = []
            for t in TOLERANCES:
                s = _dp(pts, t)
                bands.append(s if len(s) >= 4 else [])
            row = {"c": c, "a": round(km2, 3), "b": [min(lats), min(lons), max(lats), max(lons)], "p": bands}
            _names(a.tags, row)
            self.rows.append(row)


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else SRC
    if not src.exists():
        print(f"Missing {src}. Download it first (see build_roads.py).")
        return 1
    t0 = time.time()
    h = Water()
    h.apply_file(str(src), locations=True, idx="flex_mem")
    counts: dict = {}
    for r in h.rows:
        counts[r["c"]] = counts.get(r["c"], 0) + 1
    meta = {
        "source": "OpenStreetMap via Geofabrik (pakistan-latest.osm.pbf)",
        "attribution": "© OpenStreetMap contributors (ODbL)",
        "extract_date": datetime.fromtimestamp(src.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d"),
        "built": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "counts": counts,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        json.dump({"meta": meta, "water": h.rows}, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(h.rows)} features -> {OUT} ({OUT.stat().st_size / 1e6:.1f} MB) in {time.time() - t0:.0f}s")
    print(counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
