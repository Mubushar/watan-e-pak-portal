"""
Turn-by-turn directions on real roads (the map's route finder).

Uses the OpenStreetMap routing servers run by FOSSGIS (routing.openstreetmap.de, OSRM
profiles for car, bike and foot) when ``ROUTING_ONLINE`` is on (the default); otherwise, or
if they can't be reached, falls back to the portal's own road-class router
(``server.gis_route``, approximate). Results are cached; driving times include a typical
city traffic factor.

Settings (environment variables, or ``backend/.env``)::

    ROUTING_ONLINE=1                                  # 0 = never call an outside router
    ROUTING_URL=https://routing.openstreetmap.de      # OSRM base (routed-car|bike|foot paths)
    ROUTING_TRAFFIC_FACTOR=1.25                       # typical city traffic for driving times
"""

from __future__ import annotations

import json
import os
import threading
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

import httpx

import envfile  # noqa: F401  (loads backend/.env)

ONLINE = os.getenv("ROUTING_ONLINE", "1").strip().lower() in ("1", "true", "yes", "on")
BASE = os.getenv("ROUTING_URL", "https://routing.openstreetmap.de").rstrip("/")
TRAFFIC = float(os.getenv("ROUTING_TRAFFIC_FACTOR", "1.25") or 1.0)
PROFILES = {"drive": "routed-car", "bike": "routed-bike", "walk": "routed-foot"}
ATTRIBUTION = "Routing © OpenStreetMap contributors, FOSSGIS routing service"

_cache: "OrderedDict[Tuple[Any, ...], Dict[str, Any]]" = OrderedDict()
_lock = threading.Lock()

_TURN = {"left": "left", "right": "right", "slight left": "slightly left", "slight right": "slightly right",
         "sharp left": "sharp left", "sharp right": "sharp right", "straight": "straight", "uturn": "around"}


def _fmt_duration(s: float) -> str:
    m = round(s / 60)
    if m < 60:
        return f"{max(1, m)} min"
    return f"{m // 60} h {m % 60} min" if m % 60 else f"{m // 60} h"


def _fmt_distance(m: float) -> str:
    return f"{round(m)} m" if m < 1000 else f"{m / 1000:.1f} km"


def _heading(b: float) -> str:
    return ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"][round(b / 45) % 8]


def _ordinal(n: int) -> str:
    return {1: "1st", 2: "2nd", 3: "3rd"}.get(n, f"{n}th")


def _instruction(step: Dict[str, Any]) -> str:
    man = step.get("maneuver", {})
    kind, mod = man.get("type", ""), man.get("modifier", "")
    road = step.get("name") or step.get("ref") or ""
    on = f" onto {road}" if road else ""
    turn = _TURN.get(mod, mod)
    if kind == "depart":
        return f"Head {_heading(man.get('bearing_after', 0))}" + (f" on {road}" if road else "")
    if kind == "arrive":
        return "Arrive at your destination"
    if kind in ("roundabout", "rotary", "roundabout turn"):
        n = man.get("exit")
        return f"At the roundabout, take the {_ordinal(n)} exit{on}" if n else f"Go through the roundabout{on}"
    if kind == "merge":
        return f"Merge {turn}{on}".strip()
    if kind in ("on ramp", "off ramp"):
        return f"Take the {'ramp' if kind == 'on ramp' else 'exit'}{' ' + turn if turn else ''}{on}"
    if kind == "fork":
        return f"Keep {turn}{on}"
    if kind == "end of road":
        return f"At the end of the road, turn {turn}{on}"
    if kind in ("continue", "new name") or mod == "straight":
        return f"Continue{on or ' straight'}"
    return f"Turn {turn}{on}" if turn else f"Continue{on}"


def _osrm(a: Tuple[float, float], b: Tuple[float, float], mode: str, alternatives: bool) -> Optional[List[Dict[str, Any]]]:
    url = f"{BASE}/{PROFILES[mode]}/route/v1/driving/{a[1]:.6f},{a[0]:.6f};{b[1]:.6f},{b[0]:.6f}"
    try:
        r = httpx.get(url, timeout=12, headers={"User-Agent": "Watan-e-Pak/1.0 (real-estate portal)"},
                      params={"overview": "full", "geometries": "geojson", "steps": "true",
                              "alternatives": "true" if alternatives else "false"})
        data = r.json() if r.status_code == 200 else {}
    except (httpx.HTTPError, ValueError):
        return None
    if data.get("code") != "Ok":
        return None
    factor = TRAFFIC if mode == "drive" else 1.0
    routes = []
    for i, rt in enumerate(data.get("routes", [])[:3]):
        steps = []
        for leg in rt.get("legs", []):
            for st in leg.get("steps", []):
                dist = st.get("distance", 0)
                steps.append({"instruction": _instruction(st), "road": st.get("name") or None,
                              "distance_m": round(dist), "distance_text": _fmt_distance(dist),
                              "duration_s": round(st.get("duration", 0) * factor)})
        longest = sorted((s for s in steps if s["road"]), key=lambda s: -s["distance_m"])
        dur = rt.get("duration", 0) * factor
        routes.append({"label": "Fastest" if i == 0 else f"Alternative {i}",
                       "distance_m": round(rt.get("distance", 0)), "distance_text": _fmt_distance(rt.get("distance", 0)),
                       "duration_s": round(dur), "duration_text": _fmt_duration(dur),
                       "via": list(dict.fromkeys(s["road"] for s in longest))[:2],
                       "geometry": [[round(c[1], 6), round(c[0], 6)] for c in rt["geometry"]["coordinates"]],
                       "steps": steps})
    return routes


def _portal(a: Tuple[float, float], b: Tuple[float, float], mode: str) -> List[Dict[str, Any]]:
    import server as core  # local import: server is heavy and imports this module's siblings

    data = json.loads(core.gis_route(a[0], a[1], b[0], b[1], mode="walk" if mode == "bike" else mode, alternatives=2))
    out = []
    for i, leg in enumerate([data.get("best"), *(data.get("alternatives") or [])]):
        if not leg:
            continue
        out.append({"label": "Fastest" if i == 0 else f"Alternative {i}", "distance_m": round(leg["distance_m"]),
                    "distance_text": _fmt_distance(leg["distance_m"]), "duration_s": round(leg["duration_s"]),
                    "duration_text": _fmt_duration(leg["duration_s"]), "via": [], "geometry": leg["geometry"],
                    "steps": [{"instruction": s.get("instruction", ""), "road": None, "distance_m": round(s.get("distance_m", 0)),
                               "distance_text": _fmt_distance(s.get("distance_m", 0)), "duration_s": round(s.get("duration_s", 0))}
                              for s in leg.get("steps", [])]})
    return out


def directions(a: Tuple[float, float], b: Tuple[float, float], mode: str = "drive", alternatives: bool = True) -> Dict[str, Any]:
    """Routes from a to b ((lat, lon) pairs): fastest first, with turn-by-turn steps."""
    mode = mode if mode in PROFILES else "drive"
    key = (round(a[0], 5), round(a[1], 5), round(b[0], 5), round(b[1], 5), mode, alternatives)
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    routes = _osrm(a, b, mode, alternatives) if ONLINE else None
    source = "osm"
    if not routes:
        routes, source = _portal(a, b, mode), "portal"
    out = {"mode": mode, "source": source, "traffic_factor": TRAFFIC if mode == "drive" else 1.0, "routes": routes,
           "attribution": ATTRIBUTION if source == "osm" else "Portal road-class router (approximate)"}
    with _lock:
        _cache[key] = out
        while len(_cache) > 300:
            _cache.popitem(last=False)
    return out
