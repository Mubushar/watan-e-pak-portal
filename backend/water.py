"""
Pakistan's water bodies for the map (built by ``build_water.py`` from OpenStreetMap):
rivers, canals, lakes, reservoirs, river beds and ponds.

``in_view()`` returns what crosses a map view, thinned by zoom so the country view stays light:

    zoom ≤ 6    named rivers; water areas ≥ 3 km² (Tarbela, Mangla, Indus river bed …)
    zoom 7–8    + named canals; areas ≥ 0.3 km²
    zoom 9–11   + every river and canal; areas ≥ 0.03 km²
    zoom ≥ 12   everything, full detail
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import storage

DATA = Path(__file__).with_name("media") / "water" / "pk_water.json"
AREA_CLASSES = ("lake", "reservoir", "riverbed", "pond")
MAX_FEATURES = 6000


def available() -> bool:
    return DATA.exists() or storage.has_asset("seed/media/water/pk_water.json")


@lru_cache(maxsize=1)
def _load() -> Dict[str, Any]:
    raw = storage.read_seed_asset("media/water/pk_water.json", str(DATA))
    return json.loads(raw.decode("utf-8")) if raw else {"meta": {}, "features": []}


def meta() -> Dict[str, Any]:
    return _load()["meta"] if available() else {}


def _rules(zoom: int) -> Tuple[int, float, bool, bool, bool]:
    """(band, min area km², all rivers, named canals, all canals)."""
    if zoom <= 6:
        return 0, 3.0, False, False, False
    if zoom <= 8:
        return 1, 0.3, False, True, False
    if zoom <= 11:
        return 2, 0.03, True, True, True
    return 3, 0.0, True, True, True


@lru_cache(maxsize=256)
def _query(s: float, w: float, n: float, e: float, zoom: int, classes: Tuple[str, ...]) -> Dict[str, Any]:
    band, min_area, all_rivers, named_canals, all_canals = _rules(zoom)
    out: List[Dict[str, Any]] = []
    for r in _load()["water"]:
        c = r["c"]
        if classes and c not in classes:
            continue
        if c in AREA_CLASSES:
            if r.get("a", 0) < min_area:
                continue
        elif c == "river":
            if not (all_rivers or r.get("n")):
                continue
        elif c == "canal":
            if not (all_canals or (named_canals and r.get("n"))):
                continue
        b = r["b"]
        if b[0] > n or b[2] < s or b[1] > e or b[3] < w:
            continue
        pts = r["p"][band]
        if not pts:
            continue
        row = {k: v for k, v in r.items() if k not in ("p", "b")}
        row["p"] = pts
        out.append(row)
    truncated = len(out) > MAX_FEATURES
    if truncated:
        # Keep the big areas and named features first.
        out.sort(key=lambda r: (-(r.get("a") or 0), 0 if r.get("n") else 1))
        out = out[:MAX_FEATURES]
    return {"count": len(out), "truncated": truncated, "zoom_band": band, "water": out}


def in_view(south: float, west: float, north: float, east: float, zoom: int,
            classes: Optional[List[str]] = None) -> Dict[str, Any]:
    if not available():
        return {"count": 0, "water": [], "missing": True,
                "hint": "Water data not built yet: run build_water.py (see backend/README.md)."}
    q = 0.25 if zoom <= 8 else 0.05
    s, w = (int(south / q) - 1) * q, (int(west / q) - 1) * q
    n, e = (int(north / q) + 1) * q, (int(east / q) + 1) * q
    res = _query(round(s, 3), round(w, 3), round(n, 3), round(e, 3), int(zoom), tuple(sorted(classes or ())))
    return {**res, "meta": meta()}
