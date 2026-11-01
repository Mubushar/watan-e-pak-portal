"""
Administration of the property database: every field of every listing, for staff with
``properties.manage`` (REST: /admin/properties*).

* ``query()``  — search, filter, sort and page the whole catalogue, with facet counts
* ``save()``   — create or update one listing with full validation (city → scheme → block chain,
                 price, coordinates inside Pakistan, areas kept in sync between sq ft / marla / kanal)
* ``bulk()``   — feature / unfeature, change status, assign an agent or delete many at once
* ``export_csv()`` / ``import_csv()`` — spreadsheet round-trip (import has a dry run)

Every change stamps ``updated_at``; durable storage saves it a few seconds later.
"""

from __future__ import annotations

import csv
import io
import math
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

STATUSES = ["active", "pending", "sold", "rented", "withdrawn", "draft"]
CATEGORIES = ["house", "plot", "apartment", "building", "floor", "office", "shop", "space", "warehouse", "shed"]
USE_TYPES = ["residential", "commercial", "mix"]
PURPOSES = ["sale", "rent"]
RENT_FREQUENCIES = ["monthly", "weekly"]
FURNISHING_STATUSES = ["furnished", "semi_furnished", "unfurnished"]

EDITABLE = [
    "title", "description", "price", "currency", "listing_purpose", "security_deposit", "advance_months",
    "lease_term_months", "rent_frequency", "furnishing_status", "tenant_preference", "use_type", "category", "status", "featured",
    "total_area", "covered_area", "plot_area", "marla_area", "kanal_area",
    "city_id", "scheme_id", "block_zone_area_id",
    "bedrooms", "bathrooms", "balconies", "floors",
    "street_address", "plot_number", "sector", "landmark", "latitude", "longitude",
    "agent_id", "owner_user_id", "available_from", "amenities",
]
NUMBERS = {"price", "security_deposit", "total_area", "covered_area", "plot_area", "marla_area", "kanal_area", "latitude", "longitude"}
INTEGERS = {"bedrooms", "bathrooms", "balconies", "floors", "advance_months", "lease_term_months"}
CSV_COLUMNS = ["id", "title", "listing_purpose", "price", "security_deposit", "advance_months", "lease_term_months",
               "rent_frequency", "furnishing_status", "tenant_preference", "status", "featured", "use_type", "category", "city", "scheme", "block",
               "marla_area", "kanal_area", "total_area", "covered_area", "bedrooms", "bathrooms", "floors",
               "street_address", "plot_number", "sector", "landmark", "latitude", "longitude", "agent", "amenities",
               "description", "created_at", "updated_at"]
SORTS = {"updated": "updated_at", "created": "created_at", "price": "price", "title": "title", "size": "marla_area"}


class Invalid(ValueError):
    pass


def _core() -> Any:
    import server

    return server


def _agent_name(agent_id: Optional[str]) -> Optional[str]:
    if not agent_id:
        return None
    a = next((x for x in _core().agents_db if x.id == agent_id), None)
    return a.name if a else None


def row(p: Any) -> Dict[str, Any]:
    core = _core()
    s = core.find_scheme(p.scheme_id)
    b = core.find_block(p.block_zone_area_id)
    return {
        **p.model_dump(mode="json", exclude={"image_library", "multimedia", "floor_plans", "maps"}),
        "city_name": core.city_name(p.city_id), "scheme_name": s.name if s else None, "block_name": b.name if b else None,
        "agent_name": _agent_name(p.agent_id),
        "images": len(p.image_urls or []) + len(core.image_storage.get("property", {}).get(p.id) or []),
        "price_per_marla": round(p.price / p.marla_area) if p.price and p.marla_area else None,
        "located": p.latitude is not None and p.longitude is not None,
    }


# ---------------------------------------------------------------- query


def query(q: str = "", city_id: str = "", scheme_id: str = "", status: str = "", category: str = "", use_type: str = "",
          featured: Optional[bool] = None, agent_id: str = "", located: Optional[bool] = None,
          min_price: Optional[float] = None, max_price: Optional[float] = None,
          sort: str = "updated", order: str = "desc", page: int = 1, page_size: int = 25, purpose: str = "") -> Dict[str, Any]:
    core = _core()
    needle = (q or "").strip().lower()
    rows = []
    for p in core.properties_db:
        if city_id and p.city_id != city_id or scheme_id and p.scheme_id != scheme_id:
            continue
        if status and p.status != status or category and p.category != category or use_type and p.use_type != use_type or purpose and getattr(p, "listing_purpose", "sale") != purpose:
            continue
        if featured is not None and bool(p.featured) != featured or agent_id and p.agent_id != agent_id:
            continue
        if located is not None and ((p.latitude is not None and p.longitude is not None) != located):
            continue
        if min_price is not None and p.price < min_price or max_price is not None and p.price > max_price:
            continue
        if needle:
            hay = " ".join(str(x or "") for x in (p.id, p.title, p.description, p.sector, p.street_address, p.plot_number,
                                                   p.landmark, core.city_name(p.city_id))).lower()
            if needle not in hay:
                continue
        rows.append(p)
    facets = {
        "status": _count(p.status for p in rows),
        "category": _count(p.category for p in rows),
        "city": _count(core.city_name(p.city_id) for p in rows),
    }
    key = SORTS.get(sort, "updated_at")
    blank = [p for p in rows if getattr(p, key) is None]
    rows = sorted((p for p in rows if getattr(p, key) is not None),
                  key=lambda p: (p.title or "").lower() if key == "title" else getattr(p, key),
                  reverse=order != "asc") + blank  # blanks last either way
    page_size = max(1, min(int(page_size or 25), 200))
    pages = max(1, math.ceil(len(rows) / page_size))
    page = max(1, min(int(page or 1), pages))
    start = (page - 1) * page_size
    return {"total": len(rows), "page": page, "pages": pages, "page_size": page_size, "facets": facets,
            "rows": [row(p) for p in rows[start:start + page_size]],
            "catalogue": len(core.properties_db)}


def _count(values: Iterable[Any]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for v in values:
        out[str(v)] = out.get(str(v), 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


# ---------------------------------------------------------------- validation


def _clean(data: Dict[str, Any], current: Optional[Any] = None) -> Dict[str, Any]:
    core = _core()
    out: Dict[str, Any] = {}
    for k, v in data.items():
        if k not in EDITABLE:
            continue
        if isinstance(v, str):
            v = v.strip()
            if v == "" and k not in ("title", "city_id"):
                v = None
        if k in NUMBERS and v is not None:
            try:
                v = float(v)
            except (TypeError, ValueError):
                raise Invalid(f"{k.replace('_', ' ')} must be a number")
            if not math.isfinite(v):
                raise Invalid(f"{k.replace('_', ' ')} must be a number")
        if k in INTEGERS and v is not None:
            try:
                v = int(float(v))
            except (TypeError, ValueError):
                raise Invalid(f"{k} must be a whole number")
            if not 0 <= v <= 200:
                raise Invalid(f"{k} must be between 0 and 200")
        if k == "featured":
            v = v if isinstance(v, bool) else str(v).strip().lower() in ("1", "true", "yes", "y")
        if k == "amenities" and v is not None:
            v = core._clean_amenities(v if isinstance(v, list) else [x for x in str(v).split(";")])
        if k == "available_from" and v is not None and not isinstance(v, datetime):
            try:
                v = datetime.fromisoformat(str(v))
            except ValueError:
                raise Invalid("available_from must be a date (YYYY-MM-DD)")
        out[k] = v
    merged = {**(current.model_dump() if current is not None else {}), **out}
    if not (merged.get("title") or "").strip():
        raise Invalid("A title is required")
    if len(merged["title"]) > 200:
        raise Invalid("The title is longer than 200 characters")
    if merged.get("price") is None or merged["price"] <= 0:
        raise Invalid("The price must be more than zero")
    if merged["price"] > 1e12:
        raise Invalid("That price is not realistic")
    if merged.get("security_deposit") is not None and merged["security_deposit"] < 0:
        raise Invalid("Security deposit can't be negative")
    for key in ("advance_months", "lease_term_months"):
        if merged.get(key) is not None and not 0 <= merged[key] <= 120:
            raise Invalid(f"{key.replace('_', ' ')} must be between 0 and 120")
    if merged.get("tenant_preference") and len(merged["tenant_preference"]) > 500:
        raise Invalid("Tenant preference must be 500 characters or fewer")
    if not core.find_city(merged.get("city_id")):
        raise Invalid("Choose a valid city")
    if merged.get("scheme_id"):
        s = core.find_scheme(merged["scheme_id"])
        if not s:
            raise Invalid("That housing scheme doesn't exist")
        if s.city_id != merged["city_id"]:
            raise Invalid(f"{s.name} is not in {core.city_name(merged['city_id'])}")
    if merged.get("block_zone_area_id"):
        b = core.find_block(merged["block_zone_area_id"])
        if not b:
            raise Invalid("That block / zone doesn't exist")
        if b.scheme_id != merged.get("scheme_id"):
            raise Invalid("The block must belong to the chosen scheme")
    for k, allowed in (("status", STATUSES), ("category", CATEGORIES), ("use_type", USE_TYPES),
                       ("listing_purpose", PURPOSES), ("rent_frequency", RENT_FREQUENCIES),
                       ("furnishing_status", FURNISHING_STATUSES)):
        if merged.get(k) and merged[k] not in allowed:
            raise Invalid(f"{k.replace('_', ' ')} must be one of: {', '.join(allowed)}")
    lat, lon = merged.get("latitude"), merged.get("longitude")
    if (lat is None) != (lon is None):
        raise Invalid("Give both latitude and longitude, or neither")
    if lat is not None and not (23.0 <= lat <= 37.5 and 60.0 <= lon <= 78.0):
        raise Invalid("The location must be inside Pakistan (latitude 23–37.5, longitude 60–78)")
    if merged.get("agent_id") and not any(a.id == merged["agent_id"] for a in core.agents_db):
        raise Invalid("That agent doesn't exist")
    for k in ("marla_area", "kanal_area", "total_area", "covered_area", "plot_area"):
        if merged.get(k) is not None and merged[k] < 0:
            raise Invalid(f"{k.replace('_', ' ')} can't be negative")
    return out


def _sync_areas(p: Any, changed: Dict[str, Any]) -> None:
    """The size the admin typed wins; the other units follow it."""
    if "marla_area" in changed and changed["marla_area"] is not None:
        p.kanal_area, p.total_area = None, None
    elif "kanal_area" in changed and changed["kanal_area"] is not None:
        p.marla_area, p.total_area = None, None
    elif "total_area" in changed and changed["total_area"] is not None:
        p.marla_area, p.kanal_area = None, None
    _core().derive_areas(p)


# ---------------------------------------------------------------- write


def get(property_id: str) -> Optional[Dict[str, Any]]:
    p = _core().find_property(property_id)
    return row(p) if p else None


def save(data: Dict[str, Any], property_id: Optional[str] = None) -> Dict[str, Any]:
    core = _core()
    current = core.find_property(property_id) if property_id else None
    if property_id and not current:
        raise KeyError(property_id)
    changes = _clean(data, current)
    if current is None:
        p = core.Property(**{k: v for k, v in changes.items() if v is not None or k in ("scheme_id",)})
        _sync_areas(p, changes)
        core.properties_db.append(p)
        return {"created": True, "property": row(p)}
    for k, v in changes.items():
        setattr(current, k, v)
    _sync_areas(current, changes)
    current.updated_at = datetime.now()
    return {"updated": True, "changed": sorted(changes), "property": row(current)}


def bulk(ids: List[str], action: str, value: Any = None) -> Dict[str, Any]:
    core = _core()
    wanted = set(ids or [])
    targets = [p for p in core.properties_db if p.id in wanted]
    if not targets:
        raise Invalid("None of those listings exist")
    if action == "delete":
        core.properties_db[:] = [p for p in core.properties_db if p.id not in wanted]
        for p in targets:
            core.image_storage.get("property", {}).pop(p.id, None)
        return {"action": action, "affected": len(targets)}
    now = datetime.now()
    if action in ("feature", "unfeature"):
        for p in targets:
            p.featured, p.updated_at = action == "feature", now
    elif action == "status":
        if value not in STATUSES:
            raise Invalid(f"status must be one of: {', '.join(STATUSES)}")
        for p in targets:
            p.status, p.updated_at = value, now
    elif action == "assign_agent":
        if value and not any(a.id == value for a in core.agents_db):
            raise Invalid("That agent doesn't exist")
        for p in targets:
            p.agent_id, p.updated_at = value or None, now
    else:
        raise Invalid("action must be feature, unfeature, status, assign_agent or delete")
    return {"action": action, "affected": len(targets)}


# ---------------------------------------------------------------- CSV


def export_csv(rows: Optional[List[Dict[str, Any]]] = None) -> str:
    rows = rows if rows is not None else [row(p) for p in _core().properties_db]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({**r, "city": r.get("city_name"), "scheme": r.get("scheme_name"), "block": r.get("block_name"),
                    "agent": r.get("agent_name"), "amenities": "; ".join(r.get("amenities") or [])})
    return buf.getvalue()


def _lookup(kind: str, name: Optional[str], city_id: Optional[str] = None, scheme_id: Optional[str] = None) -> Optional[str]:
    core = _core()
    if not name:
        return None
    n = name.strip().lower()
    if kind == "city":
        c = next((c for c in core.cities_db if c.name.lower() == n or c.id == name), None)
        return c.id if c else None
    if kind == "scheme":
        s = next((s for s in core.housing_schemes_db if (s.name.lower() == n or s.id == name) and (not city_id or s.city_id == city_id)), None)
        return s.id if s else None
    if kind == "block":
        b = next((b for b in core.block_zone_areas_db if (b.name.lower() == n or b.id == name) and (not scheme_id or b.scheme_id == scheme_id)), None)
        return b.id if b else None
    a = next((a for a in core.agents_db if a.name.lower() == n or a.id == name), None)
    return a.id if a else None


def import_csv(text: str, dry_run: bool = True) -> Dict[str, Any]:
    """Create new listings, or update existing ones (rows with an ``id``), from a CSV in the
    export's format. Cities, schemes, blocks and agents are matched by name. Nothing is saved
    when any row is invalid, or with ``dry_run``."""
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    if not reader.fieldnames or "title" not in [f.strip().lower() for f in reader.fieldnames]:
        raise Invalid("The CSV needs a header row with at least title, price and city")
    plans: List[Tuple[Optional[str], Dict[str, Any]]] = []
    errors: List[Dict[str, Any]] = []
    for i, raw in enumerate(reader, start=2):
        if i > 5001:
            raise Invalid("At most 5,000 rows per import")
        r = {k.strip().lower(): (v or "").strip() for k, v in raw.items() if k}
        try:
            city_id = _lookup("city", r.get("city"))
            if not city_id:
                raise Invalid(f"unknown city '{r.get('city')}'")
            scheme_id = _lookup("scheme", r.get("scheme"), city_id=city_id)
            if r.get("scheme") and not scheme_id:
                raise Invalid(f"unknown scheme '{r.get('scheme')}' in {r.get('city')}")
            data = {k: r[k] for k in EDITABLE if k in r and r[k] != ""}
            data.update(city_id=city_id, scheme_id=scheme_id,
                        block_zone_area_id=_lookup("block", r.get("block"), scheme_id=scheme_id))
            if r.get("agent"):
                data["agent_id"] = _lookup("agent", r["agent"])
                if not data["agent_id"]:
                    raise Invalid(f"unknown agent '{r['agent']}'")
            pid = r.get("id") or None
            current = _core().find_property(pid) if pid else None
            if pid and not current:
                raise Invalid(f"no listing with id {pid}")
            _clean(data, current)
            plans.append((pid, data))
        except Invalid as exc:
            errors.append({"row": i, "error": str(exc)})
    summary = {"rows": len(plans) + len(errors), "valid": len(plans), "errors": errors[:50],
               "would_create": sum(1 for pid, _ in plans if not pid), "would_update": sum(1 for pid, _ in plans if pid)}
    if dry_run or errors:
        return {"dry_run": True, "saved": False, **summary}
    for pid, data in plans:
        save(data, pid)
    return {"dry_run": False, "saved": True, **summary}
