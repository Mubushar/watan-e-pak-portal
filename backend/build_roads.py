"""
Build Pakistan's main road network for the portal map from OpenStreetMap.

Source: Geofabrik's daily OpenStreetMap extract for Pakistan
(https://download.geofabrik.de/asia/pakistan-latest.osm.pbf, © OpenStreetMap contributors,
ODbL). Keeps motorways, trunk roads / national highways, primary and secondary roads, plus
those under construction, with their number (M-2, N-5 …), English / Urdu name, lanes, speed
limit and surface. Each road is simplified for four zoom bands so the map stays fast.

Output: ``media/roads/pk_roads.json`` (git-ignored; served by ``roads.py`` / ``GET /geo/roads``).

Run (pyosmium has wheels for Python 3.12, not the backend's newer Python):

    curl -L -o media/osm/pakistan-latest.osm.pbf https://download.geofabrik.de/asia/pakistan-latest.osm.pbf
    uv run --no-project --python 3.12 --with osmium python build_roads.py

Re-run any time to pick up new roads; then restart the backend.
"""

from __future__ import annotations

import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import osmium

HERE = Path(__file__).parent
SRC = HERE / "media" / "osm" / "pakistan-latest.osm.pbf"
OUT = HERE / "media" / "roads" / "pk_roads.json"

CLASSES = ("motorway", "trunk", "primary", "secondary")
# Simplification tolerance (degrees) per zoom band: country, region, city, street.
TOLERANCES = (0.006, 0.002, 0.0006, 0.00008)


def _dp(pts: list, tol: float) -> list:
    """Douglas-Peucker simplification of [[lat, lon], ...] (iterative)."""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    kx = math.cos(math.radians(pts[0][0]))
    while stack:
        a, b = stack.pop()
        ay, ax = pts[a][0], pts[a][1] * kx
        by, bx = pts[b][0], pts[b][1] * kx
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy) or 1e-12
        best, idx = -1.0, -1
        for i in range(a + 1, b):
            py, px = pts[i][0], pts[i][1] * kx
            d = abs(dy * px - dx * py + bx * ay - by * ax) / L
            if d > best:
                best, idx = d, i
        if best > tol and idx > 0:
            keep[idx] = True
            stack.append((a, idx))
            stack.append((idx, b))
    return [p for p, k in zip(pts, keep) if k]


class Roads(osmium.SimpleHandler):
    def __init__(self) -> None:
        super().__init__()
        self.roads: list = []

    def way(self, w) -> None:  # noqa: ANN001
        hw = w.tags.get("highway")
        status = "open"
        if hw == "construction":
            hw, status = w.tags.get("construction"), "construction"
        elif hw in ("proposed",):
            return
        if hw not in CLASSES:
            return
        pts = []
        for n in w.nodes:
            if n.location.valid():
                pts.append([round(n.location.lat, 5), round(n.location.lon, 5)])
        if len(pts) < 2:
            return
        lats = [p[0] for p in pts]
        lons = [p[1] for p in pts]
        r = {
            "c": hw,
            "b": [min(lats), min(lons), max(lats), max(lons)],
            "p": [_dp(pts, t) for t in TOLERANCES],
        }
        if status != "open":
            r["s"] = status
        for key, tag in (("r", "ref"), ("n", "name:en"), ("u", "name:ur"), ("l", "lanes"), ("v", "maxspeed"), ("f", "surface")):
            v = w.tags.get(tag)
            if v:
                r[key] = v
        if "n" not in r and w.tags.get("name"):
            r["n"] = w.tags.get("name")
        self.roads.append(r)


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else SRC
    if not src.exists():
        print(f"Missing {src}. Download it first (see the docstring).")
        return 1
    t0 = time.time()
    h = Roads()
    h.apply_file(str(src), locations=True, idx="flex_mem")
    roads = h.roads
    OUT.parent.mkdir(parents=True, exist_ok=True)
    counts: dict = {}
    for r in roads:
        k = r["c"] + ("/construction" if r.get("s") else "")
        counts[k] = counts.get(k, 0) + 1
    meta = {
        "source": "OpenStreetMap via Geofabrik (pakistan-latest.osm.pbf)",
        "attribution": "© OpenStreetMap contributors (ODbL)",
        "extract_date": datetime.fromtimestamp(src.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d"),
        "built": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "tolerances": TOLERANCES,
        "counts": counts,
    }
    with OUT.open("w", encoding="utf-8") as f:
        json.dump({"meta": meta, "roads": roads}, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(roads)} roads -> {OUT} ({OUT.stat().st_size / 1e6:.1f} MB) in {time.time() - t0:.0f}s")
    print(counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
