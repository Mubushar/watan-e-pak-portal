"""
Base data: the portal's cities, housing schemes / societies and their blocks / zones.

* ``create`` / ``update`` / ``delete`` / ``get`` / ``rows`` for the admin screens
  (``/admin/basedata/{table}``), validated against the models; a record that others depend on
  (a city with schemes or listings, a scheme with blocks or listings) can't be deleted.
* ``load_seed()`` merges the researched reference data (``geodata/pk_cities_basedata.json``,
  ``geodata/pk_housing_schemes.json`` — census figures, development authorities, approval
  status with its source) into the in-memory tables at start-up: existing records with the
  same name are enriched, new ones are added.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import server as core

GEODATA = Path(__file__).with_name("geodata")
CITIES_FILE = GEODATA / "pk_cities_basedata.json"
SCHEMES_FILE = GEODATA / "pk_housing_schemes.json"

APPROVAL_STATUSES = ["approved", "noc_issued", "partially_approved", "under_process", "unapproved", "illegal", "cancelled"]
DEVELOPMENT_STATUSES = ["developed", "under development", "planned"]
SYSTEM_FIELDS = {"id", "created_at", "updated_at", "image_urls", "maps", "floor_plans", "image_library", "amenities", "multimedia"}


def _tables() -> Dict[str, Tuple[Any, List[Any]]]:
    return {
        "cities": (core.City, core.cities_db),
        "schemes": (core.HousingScheme, core.housing_schemes_db),
        "blocks": (core.BlockZoneArea, core.block_zone_areas_db),
    }


def _norm(s: Optional[str]) -> str:
    return " ".join((s or "").lower().replace("-", " ").split())


def fields(table: str) -> List[Dict[str, Any]]:
    """Editable fields of a table (name, type, required) for the admin forms."""
    model, _ = _tables()[table]
    out = []
    for name, f in model.model_fields.items():
        if name in SYSTEM_FIELDS:
            continue
        out.append({"name": name, "type": str(f.annotation).replace("typing.", ""), "required": f.is_required()})
    return out


def _row(table: str, rec: Any) -> Dict[str, Any]:
    d = core.model_dict(rec)
    if table == "cities":
        d["schemes"] = sum(1 for s in core.housing_schemes_db if s.city_id == rec.id)
        d["properties"] = sum(1 for p in core.properties_db if p.city_id == rec.id)
    elif table == "schemes":
        d["city"] = core.city_name(rec.city_id)
        d["blocks"] = sum(1 for b in core.block_zone_areas_db if b.scheme_id == rec.id)
        d["properties"] = sum(1 for p in core.properties_db if getattr(p, "scheme_id", None) == rec.id)
    elif table == "blocks":
        sch = core.find_scheme(rec.scheme_id)
        d["scheme"] = sch.name if sch else None
    return d


def rows(table: str, q: Optional[str] = None, city_id: Optional[str] = None, scheme_id: Optional[str] = None) -> List[Dict[str, Any]]:
    _, db = _tables()[table]
    out = []
    for r in db:
        if city_id and getattr(r, "city_id", None) != city_id:
            continue
        if scheme_id and getattr(r, "scheme_id", None) != scheme_id:
            continue
        if q and _norm(q) not in _norm(f"{r.name} {getattr(r, 'name_ur', '') or ''} {getattr(r, 'developer', '') or ''} {getattr(r, 'state', '') or ''}"):
            continue
        out.append(_row(table, r))
    # the portal's order: Islamabad first, the DHA / Bahria phases first among societies
    import priority

    if table == "cities":
        return priority.sort_cities(out)
    if table == "schemes":
        pops = {c.id: (c.name, c.population) for c in core.cities_db}
        return sorted(out, key=lambda d: priority.society_key(d["name"], *pops.get(d.get("city_id"), (d.get("city"), None)),
                                                             d.get("properties") or 0, d.get("total_units")))
    return sorted(out, key=lambda d: d["name"].lower())


def get(table: str, record_id: str) -> Optional[Dict[str, Any]]:
    _, db = _tables()[table]
    rec = next((r for r in db if r.id == record_id), None)
    return _row(table, rec) if rec else None


def _clean(table: str, data: Dict[str, Any]) -> Dict[str, Any]:
    model, _ = _tables()[table]
    allowed = set(model.model_fields) - SYSTEM_FIELDS
    unknown = set(data) - allowed - {"schemes", "properties", "blocks", "city", "scheme"}
    if unknown:
        raise ValueError(f"Unknown field(s): {', '.join(sorted(unknown))}")
    clean = {k: v for k, v in data.items() if k in allowed}
    for k in ("name", "name_ur", "description", "developer"):
        if isinstance(clean.get(k), str):
            clean[k] = clean[k].strip() or None
    if table == "schemes":
        if clean.get("approval_status") not in (None, *APPROVAL_STATUSES):
            raise ValueError(f"approval_status must be one of {APPROVAL_STATUSES}")
        if "city_id" in clean and not core.find_city(clean["city_id"]):
            raise ValueError("City not found")
    if table == "blocks" and "scheme_id" in clean and not core.find_scheme(clean["scheme_id"]):
        raise ValueError("Housing scheme not found")
    return clean


def create(table: str, data: Dict[str, Any]) -> Dict[str, Any]:
    model, db = _tables()[table]
    clean = _clean(table, data)
    if not clean.get("name"):
        raise ValueError("Name is required")
    dup = next((r for r in db if _norm(r.name) == _norm(clean["name"])
                and getattr(r, "city_id", None) == clean.get("city_id") and getattr(r, "scheme_id", None) == clean.get("scheme_id")), None)
    if dup:
        raise ValueError(f"“{clean['name']}” already exists")
    rec = model(**clean)
    db.append(rec)
    return _row(table, rec)


def update(table: str, record_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    model, db = _tables()[table]
    rec = next((r for r in db if r.id == record_id), None)
    if rec is None:
        return None
    clean = _clean(table, data)
    if "name" in clean and not clean["name"]:
        raise ValueError("Name is required")
    merged = model.model_validate({**core.model_dict(rec), **clean})  # type checks
    for k in clean:
        setattr(rec, k, getattr(merged, k))
    if hasattr(rec, "updated_at"):
        rec.updated_at = datetime.now()
    return _row(table, rec)


def dependents(table: str, record_id: str) -> Dict[str, int]:
    if table == "cities":
        return {"schemes": sum(1 for s in core.housing_schemes_db if s.city_id == record_id),
                "properties": sum(1 for p in core.properties_db if p.city_id == record_id)}
    if table == "schemes":
        return {"blocks": sum(1 for b in core.block_zone_areas_db if b.scheme_id == record_id),
                "properties": sum(1 for p in core.properties_db if getattr(p, "scheme_id", None) == record_id)}
    return {"properties": sum(1 for p in core.properties_db if getattr(p, "block_zone_area_id", None) == record_id)}


def delete(table: str, record_id: str) -> Dict[str, Any]:
    """Delete a record; refused (``blocked``) while other records depend on it."""
    _, db = _tables()[table]
    rec = next((r for r in db if r.id == record_id), None)
    if rec is None:
        return {"error": "not_found"}
    deps = {k: v for k, v in dependents(table, record_id).items() if v}
    if deps:
        return {"error": "blocked", "dependents": deps}
    db[:] = [r for r in db if r.id != record_id]
    return {"deleted": True, "id": record_id, "name": rec.name}


# ------------------------------------------------------------------ researched seed data

CITY_ALIASES = {"wah": "wah cantonment", "nawabshah": "shaheed benazirabad", "mingora": "swat"}


def _city_by_name(name: str) -> Optional[Any]:
    n = _norm(name)
    return next((c for c in core.cities_db if _norm(c.name) in (n, CITY_ALIASES.get(n, n))), None)


def load_seed() -> Dict[str, int]:
    """Merge the researched cities and schemes into the tables (idempotent)."""
    stats = {"cities_added": 0, "cities_updated": 0, "schemes_added": 0, "schemes_updated": 0}
    if CITIES_FILE.exists():
        for row in json.loads(CITIES_FILE.read_text(encoding="utf-8")):
            data = {
                "name": row["name"], "name_ur": row.get("name_ur"), "state": row.get("province"), "district": row.get("district"),
                "latitude": row.get("latitude"), "longitude": row.get("longitude"), "description": row.get("description"),
                "population": row.get("population_2023"), "population_note": row.get("population_note"),
                "area_km2": row.get("area_km2"), "development_authority": row.get("development_authority"),
                "sources": row.get("sources") or [],
            }
            data = {k: v for k, v in data.items() if v not in (None, "", [])}
            city = _city_by_name(row["name"])
            if city:
                for k, v in data.items():
                    if k != "name":
                        setattr(city, k, v)
                stats["cities_updated"] += 1
            else:
                core.cities_db.append(core.City(**data))
                stats["cities_added"] += 1
    if SCHEMES_FILE.exists():
        for row in json.loads(SCHEMES_FILE.read_text(encoding="utf-8")):
            city = _city_by_name(row.get("city") or "")
            if city is None:
                continue
            data = {
                "name": row["name"], "name_ur": row.get("name_ur"), "city_id": city.id, "developer": row.get("developer"),
                "approval_authority": row.get("approval_authority"), "approval_status": row.get("approval_status"),
                "approval_note": row.get("approval_note"), "established_year": row.get("established_year"),
                "area_acres": row.get("area_acres"), "total_units": row.get("total_units"), "plot_sizes": row.get("plot_sizes") or [],
                "development_status": row.get("development_status"), "possession_status": row.get("possession_status"),
                "utilities": row.get("utilities") or [], "latitude": row.get("latitude"), "longitude": row.get("longitude"),
                "website": row.get("website"), "description": row.get("description"), "sources": row.get("sources") or [],
            }
            data = {k: v for k, v in data.items() if v not in (None, "", [])}
            if data.get("approval_status") not in APPROVAL_STATUSES:
                data.pop("approval_status", None)
            names = {_norm(row["name"])} | {_norm(a) for a in row.get("aliases", [])}
            existing = next((s for s in core.housing_schemes_db if s.city_id == city.id and _norm(s.name) in names), None)
            if existing is None and row.get("aliases"):
                # An alias may name a record filed under the twin city (e.g. DHA phases: Islamabad / Rawalpindi).
                aliases = {_norm(a) for a in row["aliases"]}
                existing = next((s for s in core.housing_schemes_db if _norm(s.name) in aliases), None)
            if existing:
                for k, v in data.items():
                    if k not in ("name", "city_id"):
                        setattr(existing, k, v)
                stats["schemes_updated"] += 1
            else:
                core.housing_schemes_db.append(core.HousingScheme(**data))
                stats["schemes_added"] += 1
    return stats
