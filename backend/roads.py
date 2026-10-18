"""
Pakistan's main road network for the map (built by ``build_roads.py`` from OpenStreetMap).

``in_view()`` returns the roads crossing a map view at a detail level that suits the zoom:

    zoom ≤ 6    motorways and trunk roads / national highways, coarse
    zoom 7–8    + primary roads
    zoom 9–11   + secondary roads
    zoom ≥ 12   full detail

Roads under construction are included (``s: "construction"``). The data file is optional:
without it the endpoint says how to build it.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DATA = Path(__file__).with_name("media") / "roads" / "pk_roads.json"
CLASS_RANK = {"motorway": 0, "trunk": 1, "primary": 2, "secondary": 3}
MAX_ROADS = 8000


def available() -> bool:
    return DATA.exists()


@lru_cache(maxsize=1)
def _load() -> Dict[str, Any]:
    with DATA.open(encoding="utf-8") as f:
        return json.load(f)


def meta() -> Dict[str, Any]:
    return _load()["meta"] if available() else {}


def _band(zoom: int) -> Tuple[int, int]:
    """(simplification band, highest class rank shown) for a zoom level."""
    if zoom <= 6:
        return 0, 1
    if zoom <= 8:
        return 1, 2
    if zoom <= 11:
        return 2, 3
    return 3, 3


@lru_cache(maxsize=256)
def _query(s: float, w: float, n: float, e: float, zoom: int, classes: Tuple[str, ...]) -> Dict[str, Any]:
    band, max_rank = _band(zoom)
    out: List[Dict[str, Any]] = []
    for r in _load()["roads"]:
        rank = CLASS_RANK.get(r["c"], 9)
        if rank > max_rank or (classes and r["c"] not in classes):
            continue
        b = r["b"]
        if b[0] > n or b[2] < s or b[1] > e or b[3] < w:
            continue
        row = {k: v for k, v in r.items() if k not in ("p", "b")}
        row["p"] = r["p"][band]
        out.append(row)
    truncated = len(out) > MAX_ROADS
    if truncated:
        out.sort(key=lambda r: CLASS_RANK.get(r["c"], 9))
        out = out[:MAX_ROADS]
    return {"count": len(out), "truncated": truncated, "zoom_band": band, "roads": out}


def in_view(south: float, west: float, north: float, east: float, zoom: int,
            classes: Optional[List[str]] = None) -> Dict[str, Any]:
    if not available():
        return {"count": 0, "roads": [], "missing": True,
                "hint": "Road data not built yet: download the OpenStreetMap extract and run build_roads.py (see backend/README.md)."}
    # Round the view outwards so small pans hit the cache.
    q = 0.25 if zoom <= 8 else 0.05
    s, w = (int(south / q) - 1) * q, (int(west / q) - 1) * q
    n, e = (int(north / q) + 1) * q, (int(east / q) + 1) * q
    res = _query(round(s, 3), round(w, 3), round(n, 3), round(e, 3), int(zoom), tuple(sorted(classes or ())))
    return {**res, "meta": meta()}


def search(q: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Roads whose number or name matches ``q`` (e.g. "M-2", "GT Road"), one row per number / name."""
    if not available() or not q.strip():
        return []
    ql = q.strip().lower().replace(" ", "")
    seen: Dict[str, Dict[str, Any]] = {}
    for r in _load()["roads"]:
        label = r.get("r") or r.get("n")
        if not label:
            continue
        hay = f"{r.get('r', '')}{r.get('n', '')}".lower().replace(" ", "")
        if ql not in hay:
            continue
        cur = seen.get(label)
        b = r["b"]
        if cur is None:
            seen[label] = {"label": label, "name": r.get("n"), "ref": r.get("r"), "class": r["c"], "bounds": list(b)}
        else:
            cb = cur["bounds"]
            cur["bounds"] = [min(cb[0], b[0]), min(cb[1], b[1]), max(cb[2], b[2]), max(cb[3], b[3])]
        if len(seen) >= limit:
            break
    return list(seen.values())
