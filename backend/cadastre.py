"""
Cadastre: land parcels collected on the portal's map (the "Cadastre" tools on the Map page).

A parcel is a polygon with the identifiers a Pakistani land record uses — the society plot
(society / sector / block / street / plot no.) and the revenue record (district / tehsil / mouza,
khewat, khatooni, khasra) — plus land use, status, ownership type and how it was surveyed.
Area, perimeter and edge lengths are computed from the geometry; overlaps with other parcels and
bad shapes (too few corners, self-crossing) are reported.

Parcel PIN (the parcel's ID): a 15-digit geographic code, written like a CNIC — ``XXXXX-XXXXX-XXXXX``.
  * The grid: 0.00001° cells (≈1.1 m N–S, 0.9–1.0 m E–W in Pakistan), counted from 23°N / 60°E, so the north
    and east indexes (up to 1,500,000 / 1,800,000) are 7 digits each. The smallest parcels in Pakistan —
    8×10 ft market shops, 6×6 ft kiosks, 1-marla houses — are ≥ 1.8 m wide, so neighbours never share a cell.
  * The two indexes are interleaved digit by digit (north, east, north, east …): every extra pair narrows the
    area tenfold — 4 digits ≈ 111 km, 6 ≈ 11 km, 8 ≈ 1.1 km, 10 ≈ 110 m, 12 ≈ 11 m, 14 ≈ 1 m — so parcels
    nearby share their leading digits, like a postal PIN, and sorting by PIN groups them by area.
  * Digit 15 is a Damm check digit (catches every single wrong digit and swap of neighbouring digits).
  * The point coded is inside the parcel (its centre, or an interior point for an L-shaped / concave one).
  * Two parcels in the same 1 m cell (or strata units in one building) get a suffix: -01, -02 …
  * Reshaping keeps a parcel's PIN; a split / merge makes new parcels with new PINs.

Parcels live in ``server.cadastre_parcels_db`` (persisted like every ``*_db`` store) and are drawn
as the built-in "Cadastre parcels" layer (``builtin:cadastre``), which starts empty and unpublished.
"""

from __future__ import annotations

import math
import sys
import uuid
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

R = 6378137.0
SQFT_M2 = 0.09290304
SOCIETY_MARLA_SQFT = 225.0   # housing societies (and the portal's listings) use 225 sq ft
REVENUE_MARLA_SQFT = 272.25  # the revenue record (patwari) marla
LAND_USES = ["residential", "commercial", "mixed_use", "agricultural", "industrial", "amenity", "park",
             "graveyard", "mosque", "school", "health", "road", "government", "other"]
STATUSES = ["vacant", "under_construction", "built", "agricultural", "disputed", "unknown"]
PARCEL_TYPES = ["plot", "khasra_field", "building_footprint", "amenity_plot", "road_reserve", "other"]
OWNERSHIP = ["private", "society", "government", "auqaf", "shamlat", "cantonment", "unknown"]
METHODS = ["digitised_master_plan", "digitised_satellite", "gps_survey", "total_station", "imported", "other"]
TEXT_FIELDS = ["plot_no", "sector", "block", "street", "society", "city", "province", "district", "tehsil", "mouza",
               "khewat_no", "khatooni_no", "khasra_no", "declared_area", "owner_name", "source_document", "notes"]
PRIVATE_FIELDS = ("owner_name",)  # only GIS managers see who owns a parcel


def _core() -> Any:
    return sys.modules.get("server") or sys.modules.get("__main__")


def _db() -> Dict[str, Dict[str, Any]]:
    return _core().cadastre_parcels_db


# ------------------------------------------------------------------ geometry

def _local(ring: List[List[float]]) -> List[Tuple[float, float]]:
    """Corners in metres on a local plane centred on the first corner (equirectangular — fine for parcels;
    small numbers keep the arithmetic exact even for a 2 m kiosk)."""
    lat0 = sum(p[0] for p in ring) / len(ring)
    k = math.cos(math.radians(lat0))
    o = ring[0]
    return [(math.radians(p[1] - o[1]) * R * k, math.radians(p[0] - o[0]) * R) for p in ring]


def measure(ring: List[List[float]]) -> Dict[str, Any]:
    pts = _local(ring)
    n = len(pts)
    area = abs(sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))) / 2
    edges = [math.hypot(pts[(i + 1) % n][0] - pts[i][0], pts[(i + 1) % n][1] - pts[i][1]) for i in range(n)]
    sqft = area / SQFT_M2
    return {
        "area_m2": round(area, 1),
        "area_sqft": round(sqft),
        "area_marla": round(sqft / SOCIETY_MARLA_SQFT, 2),
        "area_kanal": round(sqft / SOCIETY_MARLA_SQFT / 20, 3),
        "area_marla_revenue": round(sqft / REVENUE_MARLA_SQFT, 2),
        "perimeter_m": round(sum(edges), 1),
        "edges_m": [round(e, 2) for e in edges],
        "edges_ft": [round(e / 0.3048, 1) for e in edges],
        "centroid": [round(sum(p[0] for p in ring) / n, 7), round(sum(p[1] for p in ring) / n, 7)],
    }


def _cross(a, b, c, d) -> bool:
    """Do segments ab and cd properly cross?"""
    def o(p, q, r):
        v = (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        return (v > 1e-12) - (v < -1e-12)
    return o(a, b, c) * o(a, b, d) < 0 and o(c, d, a) * o(c, d, b) < 0


def _self_crossing(pts: List[Tuple[float, float]]) -> bool:
    n = len(pts)
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue  # neighbours through the closing edge
            if _cross(a, b, pts[j], pts[(j + 1) % n]):
                return True
    return False


def _inside(p: Tuple[float, float], ring: List[Tuple[float, float]]) -> bool:
    hit = False
    for i in range(len(ring)):
        a, b = ring[i], ring[i - 1]
        if (a[1] > p[1]) != (b[1] > p[1]) and p[0] < (b[0] - a[0]) * (p[1] - a[1]) / (b[1] - a[1]) + a[0]:
            hit = not hit
    return hit


def _bbox(ring: Iterable[List[float]]) -> Tuple[float, float, float, float]:
    r = list(ring)
    return min(p[0] for p in r), min(p[1] for p in r), max(p[0] for p in r), max(p[1] for p in r)


def _overlaps(ring: List[List[float]], other: List[List[float]]) -> bool:
    a, b = _bbox(ring), _bbox(other)
    if a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1]:
        return False
    # shared edges / snapped corners are not overlaps: test with the rings shrunk a little towards their centres
    def shrink(r):
        c = (sum(p[0] for p in r) / len(r), sum(p[1] for p in r) / len(r))
        return [[c[0] + (p[0] - c[0]) * 0.97, c[1] + (p[1] - c[1]) * 0.97] for p in r]
    pa, pb = [(p[1], p[0]) for p in shrink(ring)], [(p[1], p[0]) for p in shrink(other)]
    if any(_inside(p, pb) for p in pa) or any(_inside(p, pa) for p in pb):
        return True
    return any(_cross(pa[i], pa[(i + 1) % len(pa)], pb[j], pb[(j + 1) % len(pb)]) for i in range(len(pa)) for j in range(len(pb)))


def _clean_ring(ring: Any) -> List[List[float]]:
    pts = [[float(p[0]), float(p[1])] for p in (ring or []) if isinstance(p, (list, tuple)) and len(p) >= 2]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]  # the ring is stored open
    out: List[List[float]] = []
    for p in pts:
        if not out or abs(p[0] - out[-1][0]) > 1e-9 or abs(p[1] - out[-1][1]) > 1e-9:
            out.append(p)
    return out


def check(ring: List[List[float]], skip_id: Optional[str] = None) -> Tuple[List[str], List[str]]:
    """(errors, warnings) for a parcel outline."""
    errors, warnings = [], []
    if len(ring) < 3:
        return ["A parcel needs at least 3 corners."], []
    if any(not (-90 <= p[0] <= 90 and -180 <= p[1] <= 180) for p in ring):
        return ["Corners must be [lat, lon] in degrees."], []
    if _self_crossing(_local(ring)):
        errors.append("The outline crosses itself — move the corners so the edges don't cross.")
    m = measure(ring)
    if m["area_m2"] < 5:
        errors.append("The parcel is smaller than 5 m² — check the corners.")
    if m["area_m2"] > 5_000_000:
        warnings.append("The parcel is over 500 hectares — is this one parcel?")
    hits = [p for p in _db().values() if p["id"] != skip_id and _overlaps(ring, p["ring"])]
    if hits:
        warnings.append("Overlaps " + ", ".join(_label(p) for p in hits[:5]) + (" …" if len(hits) > 5 else "") + ".")
    return errors, warnings


# ------------------------------------------------------------------ parcel PIN

PIN_ORIGIN = (23.0, 60.0)   # south-west corner of the grid (Pakistan: 23.5–37.1°N, 60.8–77.9°E)
PIN_CELL = 1e-5             # degrees (≈1 m)
PIN_LIMIT = (38.0, 78.0)
_DAMM = [[0, 3, 1, 7, 5, 9, 8, 6, 4, 2], [7, 0, 9, 2, 1, 5, 4, 8, 6, 3], [4, 2, 0, 6, 8, 7, 1, 3, 5, 9],
         [1, 7, 5, 0, 9, 8, 3, 4, 2, 6], [6, 1, 2, 3, 0, 4, 5, 9, 7, 8], [3, 6, 7, 4, 2, 0, 9, 5, 8, 1],
         [5, 8, 6, 9, 7, 2, 0, 1, 3, 4], [8, 9, 4, 5, 3, 6, 2, 0, 1, 7], [9, 4, 3, 8, 6, 1, 7, 2, 0, 5],
         [2, 5, 8, 1, 4, 3, 6, 7, 9, 0]]


def _damm(digits: str) -> int:
    i = 0
    for d in digits:
        i = _DAMM[i][int(d)]
    return i


def _pin_digits(pin: str) -> str:
    """The 15 digits of a PIN (a strata / clash suffix "-01" after them is ignored)."""
    return "".join(c for c in str(pin) if c.isdigit())[:15]


def pin_valid(pin: str) -> bool:
    d = _pin_digits(pin)
    return len(d) == 15 and _damm(d) == 0


def encode_pin(lat: float, lon: float) -> str:
    """The 15-digit PIN of the ~1 m cell containing (lat, lon), as XXXXX-XXXXX-XXXXX."""
    if not (PIN_ORIGIN[0] <= lat < PIN_LIMIT[0] and PIN_ORIGIN[1] <= lon < PIN_LIMIT[1]):
        raise ValueError("Outside Pakistan's parcel grid (23–38°N, 60–78°E)")
    n = f"{int((lat - PIN_ORIGIN[0]) / PIN_CELL + 1e-9):07d}"
    e = f"{int((lon - PIN_ORIGIN[1]) / PIN_CELL + 1e-9):07d}"
    body = "".join(a + b for a, b in zip(n, e))
    d = body + str(_damm(body))
    return f"{d[:5]}-{d[5:10]}-{d[10:]}"


def decode_pin(pin: str) -> Dict[str, Any]:
    """The cell a PIN (or a PIN prefix of 2–14 digits) stands for: its centre, edges and size."""
    digits = "".join(c for c in str(pin) if c.isdigit())
    if len(digits) >= 15:
        if _damm(digits[:15]) != 0:
            return {"error": "Check digit doesn't match — a digit is mistyped"}
        digits = digits[:14]
    if not digits:
        return {"error": "Not a parcel PIN"}
    nd, ed = digits[0::2], digits[1::2]
    span_n = 10 ** (7 - len(nd)) * PIN_CELL
    span_e = 10 ** (7 - len(ed)) * PIN_CELL
    s0 = PIN_ORIGIN[0] + int(nd.ljust(7, "0")) * PIN_CELL
    w0 = PIN_ORIGIN[1] + int(ed.ljust(7, "0")) * PIN_CELL
    return {"digits": len(digits), "south": round(s0, 6), "west": round(w0, 6), "north": round(s0 + span_n, 6),
            "east": round(w0 + span_e, 6), "center": [round(s0 + span_n / 2, 7), round(w0 + span_e / 2, 7)],
            "size_m": [round(span_n * 111_320, 1), round(span_e * 111_320 * math.cos(math.radians(s0 + span_n / 2)), 1)]}


def interior_point(ring: List[List[float]]) -> List[float]:
    """A point inside the parcel: its centroid when that is inside, else the middle of the widest
    inside stretch along the centroid's latitude (L-shaped / concave parcels)."""
    pts = _local(ring)
    n = len(pts)
    a = cx = cy = 0.0
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        f = x0 * y1 - x1 * y0
        a += f
        cx += (x0 + x1) * f
        cy += (y0 + y1) * f
    if abs(a) > 1e-9:
        cx, cy = cx / (3 * a), cy / (3 * a)
    else:
        cx, cy = sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n
    if not _inside((cx, cy), pts):
        xs = sorted(x0 + (cy - y0) * (x1 - x0) / (y1 - y0) for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1])
                    if (y0 > cy) != (y1 > cy))
        spans = [(xs[i + 1] - xs[i], (xs[i] + xs[i + 1]) / 2) for i in range(0, len(xs) - 1, 2)]
        if spans:
            cx = max(spans)[1]
    lat0 = sum(p[0] for p in ring) / len(ring)
    k = math.cos(math.radians(lat0))
    return [round(ring[0][0] + math.degrees(cy / R), 7), round(ring[0][1] + math.degrees(cx / (R * k)), 7)]


def assign_pin(ring: List[List[float]], skip_id: Optional[str] = None) -> Tuple[str, List[float]]:
    pt = interior_point(ring)
    base = encode_pin(*pt)
    taken = {q.get("pin") for q in _db().values() if q["id"] != skip_id}
    if base not in taken:
        return base, pt
    k = 1
    while f"{base}-{k:02d}" in taken:
        k += 1
    return f"{base}-{k:02d}", pt


def find_pin(pin: str) -> Dict[str, Any]:
    """A parcel by its PIN, or — for a PIN with no parcel / a prefix — the area it stands for."""
    d = _pin_digits(pin)
    suffix = str(pin).strip()[len(str(pin).strip()) - 3:] if str(pin).strip()[-3:-2] == "-" and len(d) == 15 else ""
    for q in _db().values():
        if _pin_digits(q.get("pin") or "") == d and (not suffix or str(q.get("pin", "")).endswith(suffix)):
            return {"parcel_id": q["id"], "pin": q["pin"], "area": decode_pin(d)}
    cell = decode_pin(pin)
    return cell if "error" in cell else {"parcel_id": None, "area": cell}


# ------------------------------------------------------------------ records

def _label(p: Dict[str, Any]) -> str:
    bits = [f"Plot {p['plot_no']}" if p.get("plot_no") else None, p.get("block"), p.get("society"),
            f"Khasra {p['khasra_no']}" if p.get("khasra_no") and not p.get("plot_no") else None]
    return " · ".join(b for b in bits if b) or p.get("pin") or p.get("parcel_no") or p["id"][:8]


def _next_no() -> str:
    n = 1 + max((int(p["parcel_no"].split("-")[-1]) for p in _db().values()
                 if str(p.get("parcel_no", "")).startswith("PK-CAD-") and p["parcel_no"].split("-")[-1].isdigit()), default=0)
    return f"PK-CAD-{n:06d}"


def _pick(v: Any, allowed: List[str], default: str) -> str:
    return v if v in allowed else default


def _fields(data: Dict[str, Any], cur: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    out = dict(cur or {})
    for k in TEXT_FIELDS:
        if k in data:
            v = data[k]
            out[k] = (str(v).strip()[:500] if v not in (None, "") else None)
    for k, allowed, default in (("land_use", LAND_USES, "residential"), ("status", STATUSES, "unknown"),
                                ("parcel_type", PARCEL_TYPES, "plot"), ("ownership", OWNERSHIP, "unknown"),
                                ("capture_method", METHODS, "digitised_satellite")):
        if k in data or k not in out:
            out[k] = _pick(data.get(k, out.get(k)), allowed, default)
    if "accuracy_m" in data:
        try:
            out["accuracy_m"] = round(float(data["accuracy_m"]), 2) if data["accuracy_m"] not in (None, "") else None
        except (TypeError, ValueError):
            out["accuracy_m"] = None
    if "scheme_id" in data:
        s = _core().find_scheme(data["scheme_id"]) if data["scheme_id"] else None
        out["scheme_id"] = s.id if s else None
        if s and not out.get("society"):
            out["society"] = s.name
    return out


def _who() -> Optional[str]:
    import access
    u = access.current() or {}
    return u.get("email") or u.get("name") or u.get("id")


def create(data: Dict[str, Any]) -> Dict[str, Any]:
    ring = _clean_ring(data.get("ring"))
    errors, warnings = check(ring)
    if errors:
        return {"error": " ".join(errors), "errors": errors}
    try:
        pin, pin_point = assign_pin(ring)
    except ValueError as e:
        return {"error": str(e)}
    now = datetime.now().isoformat(timespec="seconds")
    p = _fields(data)
    p.update({"id": str(uuid.uuid4()), "pin": pin, "pin_point": pin_point,
              "parcel_no": (str(data.get("parcel_no")).strip() or None) if data.get("parcel_no") else pin,
              "ring": ring, **{k: v for k, v in measure(ring).items() if k not in ("edges_ft",)},
              "verified": bool(data.get("verified")), "verified_by": _who() if data.get("verified") else None,
              "surveyed_by": _who(), "created_at": now, "updated_at": now, "version": 1})
    _db()[p["id"]] = p
    return {"parcel": public(p, True), "warnings": warnings}


def update(pid: str, data: Dict[str, Any]) -> Dict[str, Any]:
    cur = _db().get(pid)
    if not cur:
        return {"error": "Parcel not found"}
    p = _fields(data, cur)
    warnings: List[str] = []
    if "ring" in data:
        ring = _clean_ring(data["ring"])
        errors, warnings = check(ring, skip_id=pid)
        if errors:
            return {"error": " ".join(errors), "errors": errors}
        p["ring"] = ring
        p.update({k: v for k, v in measure(ring).items() if k != "edges_ft"})
    if data.get("parcel_no"):
        p["parcel_no"] = str(data["parcel_no"]).strip()
    if "verified" in data:
        p["verified"] = bool(data["verified"])
        p["verified_by"] = _who() if p["verified"] else None
    p["updated_at"] = datetime.now().isoformat(timespec="seconds")
    p["updated_by"] = _who()
    p["version"] = int(cur.get("version", 1)) + 1
    _db()[pid] = p
    return {"parcel": public(p, True), "warnings": warnings}


def delete(pid: str) -> Dict[str, Any]:
    p = _db().pop(pid, None)
    return {"deleted": True, "id": pid} if p else {"error": "Parcel not found"}


def public(p: Dict[str, Any], manager: bool) -> Dict[str, Any]:
    out = {k: v for k, v in p.items() if manager or k not in PRIVATE_FIELDS}
    out["label"] = _label(p)
    out["edges_ft"] = [round(e / 0.3048, 1) for e in p.get("edges_m") or []]
    return out


def feature(p: Dict[str, Any], manager: bool) -> Dict[str, Any]:
    props = public(p, manager)
    ring = props.pop("ring")
    return {"type": "Feature", "id": p["id"], "properties": props,
            "geometry": {"type": "Polygon", "coordinates": [[[q[1], q[0]] for q in ring + ring[:1]]]}}


def in_view(manager: bool, south: Optional[float] = None, west: Optional[float] = None, north: Optional[float] = None,
            east: Optional[float] = None, q: Optional[str] = None, limit: int = 5000) -> Dict[str, Any]:
    rows = list(_db().values())
    if None not in (south, west, north, east):
        rows = [p for p in rows if not (_bbox(p["ring"])[2] < south or _bbox(p["ring"])[0] > north
                                       or _bbox(p["ring"])[3] < west or _bbox(p["ring"])[1] > east)]
    if q:
        ql = q.lower()
        qd = "".join(c for c in q if c.isdigit())
        keys = ("pin", "parcel_no", "plot_no", "block", "sector", "society", "mouza", "khasra_no", "khewat_no", "khatooni_no")
        rows = [p for p in rows if ql in " ".join(str(p.get(k) or "") for k in keys).lower()
                or (len(qd) >= 6 and _pin_digits(p.get("pin") or "").startswith(qd))]
    return {"type": "FeatureCollection", "count": len(rows), "features": [feature(p, manager) for p in rows[:limit]]}


def summary() -> Dict[str, Any]:
    rows = list(_db().values())
    def count(k):
        c: Dict[str, int] = {}
        for p in rows:
            c[p.get(k) or "unknown"] = c.get(p.get(k) or "unknown", 0) + 1
        return dict(sorted(c.items(), key=lambda x: -x[1]))
    return {"parcels": len(rows), "verified": sum(1 for p in rows if p.get("verified")),
            "area_m2": round(sum(p.get("area_m2") or 0 for p in rows)), "by_status": count("status"),
            "by_land_use": count("land_use"), "by_society": count("society"), "by_method": count("capture_method"),
            "options": {"land_use": LAND_USES, "status": STATUSES, "parcel_type": PARCEL_TYPES, "ownership": OWNERSHIP,
                        "capture_method": METHODS},
            "units": {"marla_sqft": SOCIETY_MARLA_SQFT, "revenue_marla_sqft": REVENUE_MARLA_SQFT}}
