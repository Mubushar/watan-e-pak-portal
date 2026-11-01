"""
New projects that sell units off-plan — towers and mixed-use buildings such as China Center and
Skyra Tower (Bahria Town Phase 8) and Goldcrest Breeze Overseas (DHA Phase II) — with their live
unit inventories (``geodata/pk_project_inventory.json``, built from each project's official
website; see docs/ADMINISTRATION_GUIDE.md › "Project inventories").

``sync()`` runs at start-up, after the database has loaded, and makes the portal match the file:

* each project is a **big project** (developer, address, payment plan, offer, unit-type summary,
  price range, units available, sources, when the inventory was checked);
* each available unit is a **listing** linked to its project (``project_id`` / ``project_unit``),
  with its own size, price, floor and payment schedule, so it shows in search, on the map and in
  the AI's knowledge base;
* a unit that has left the developer's available list is marked **sold** (never deleted, so leads
  and messages about it keep their context);
* the projects also appear on the **mega-projects** map layer (type "tower").

Updating an inventory = rebuilding the JSON file and restarting (or calling ``sync()``).
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import storage

DATA = Path(__file__).with_name("geodata") / "pk_project_inventory.json"

KIND_LABEL = {"shop": "Shop", "food_court": "Food-court unit", "clinic": "Clinic / office", "apartment": "Apartment",
              "studio": "Studio apartment", "pool_apartment": "Pool apartment", "penthouse": "Duplex penthouse"}
KIND_CATEGORY = {"shop": "shop", "food_court": "shop", "clinic": "office"}
COMMERCIAL = {"shop", "food_court", "clinic"}
PROVINCE = {"Rawalpindi": "Punjab", "Islamabad": "Islamabad Capital Territory", "Lahore": "Punjab", "Karachi": "Sindh"}


def _core() -> Any:
    import server  # late: server imports this module

    return server


@lru_cache(maxsize=1)
def load() -> Dict[str, Any]:
    raw = storage.read_seed_asset("geodata/pk_project_inventory.json", str(DATA))
    return json.loads(raw.decode("utf-8")) if raw else {"projects": []}


def _money(v: float) -> str:
    return f"{v / 1e7:.2f} crore" if v >= 1e7 else f"{v / 1e5:.1f} lakh"


def _unit_label(u: Dict[str, Any]) -> str:
    beds = u.get("bedrooms")
    if u["kind"] == "apartment" and beds == 0:
        return "Studio apartment"
    if u["kind"] in ("apartment", "pool_apartment", "penthouse") and beds:
        return f"{beds}-bed {KIND_LABEL[u['kind']].lower()}"
    return KIND_LABEL.get(u["kind"], "Unit")


def unit_types(units: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group a project's available units: kind + bedrooms -> count, size range, price range."""
    groups: Dict[tuple, List[Dict[str, Any]]] = {}
    for u in units:
        groups.setdefault((u["kind"], u.get("bedrooms")), []).append(u)
    out = []
    for (kind, beds), rows in groups.items():
        prices, sizes = [r["price"] for r in rows], [r["sqft"] for r in rows]
        out.append({"kind": kind, "bedrooms": beds, "label": _unit_label(rows[0]), "available": len(rows),
                    "sqft_min": min(sizes), "sqft_max": max(sizes), "price_min": min(prices), "price_max": max(prices),
                    "layouts": sorted({r["layout"] for r in rows if r.get("layout")})})
    return sorted(out, key=lambda t: t["price_min"])


# ---------------------------------------------------------------- sync


def _city(core: Any, name: str) -> Any:
    return core.resolve_city(name) or next((c for c in core.cities_db if c.name.lower() == name.lower()), None)


def _scheme(core: Any, name: str, city_id: str) -> Any:
    """The portal's society for a name — "Johar Town" matches "Johar Town (LDA)", the same city first."""
    def norm(x: str) -> str:
        return re.sub(r"\s*\(.*?\)", "", x.lower().replace("phase viii", "phase 8")).strip()

    want = norm(name)
    if not want:
        return None
    hits = [s for s in core.housing_schemes_db
            if norm(s.name) == want or (want in norm(s.name) and len(norm(s.name)) - len(want) < 6)]
    return next((s for s in hits if s.city_id == city_id), hits[0] if hits else None)


def _description(p: Dict[str, Any], u: Dict[str, Any], checked: str) -> str:
    pay = u["payment"]
    cadence = "monthly" if pay["cadence"] == "monthly" else "quarterly"
    parts = [
        f"{_unit_label(u)} {u['unit']} on the {u['floor_label'].lower()} of {p['name']}, {p['address']}.",
        f"{u['sqft']:g} sq ft at PKR {u['rate_per_sqft']:,}/sq ft = PKR {u['price']:,} ({_money(u['price'])}).",
        f"Payment plan: PKR {pay['down']:,} down, {pay['instalments']} {cadence} instalments of PKR {pay['instalment']:,}, "
        f"PKR {pay['on_possession']:,} on possession.",
    ]
    if u.get("facing"):
        parts.append(f"{u['facing']}.")
    if p.get("offer"):
        parts.append(f"Offer: {p['offer']}.")
    parts.append(f"Developer: {p['developer']}." + (f" Marketed by {p['marketed_by']}." if p.get("marketed_by") else ""))
    parts.append(f"Availability from the developer's inventory, checked {checked}; confirm price and availability at booking.")
    return " ".join(parts)


def sync(data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Make big projects and unit listings match the inventory file (or ``data`` in the same
    shape). Safe to run any number of times."""
    core = _core()
    if data is None:
        load.cache_clear()
        data = load()
    checked = data.get("checked") or datetime.now().date().isoformat()
    stats = {"projects": 0, "created": 0, "updated": 0, "sold": 0}
    for p in data.get("projects", []):
        city = _city(core, p["city"])
        if not city:
            continue
        scheme = _scheme(core, p.get("scheme") or "", city.id)
        units = p.get("units", [])
        prices = [u["price"] for u in units]
        b = next((x for x in core.big_projects_db if x.name.lower() == p["name"].lower()), None)
        # an admin moved this project on the map: keep that position for it and its units
        pinned = (b.latitude, b.longitude) if b is not None and b.location_precision == "admin" and b.latitude is not None else None
        loc = {"lat": pinned[0], "lon": pinned[1]} if pinned else p["location"]
        fields = dict(
            description=p["description"], project_type=p["project_type"], status=p["status"], city_id=city.id,
            scheme_id=scheme.id if scheme else None, latitude=loc["lat"], longitude=loc["lon"],
            developer=p["developer"], address=p.get("address"), website=(p.get("sources") or [{}])[0].get("url"),
            marketed_by=p.get("marketed_by"), floors_label=p.get("floors"), floor_count=p.get("floor_count") or 0,
            total_units=p.get("total_units"), location_precision="admin" if pinned else p["location"]["precision"],
            payment_plan=p.get("payment_plan"), offer=p.get("offer"), unit_types=unit_types(units),
            price_from=min(prices) if prices else None, price_to=max(prices) if prices else None,
            units_available=len(units), inventory_checked=checked, inventory_source=p.get("inventory_source"),
            sources=p.get("sources") or [],
            # real images from the project's own website, credited (captions + source in multimedia)
            image_urls=[i["url"] for i in p.get("images", [])][:6],
            image_library=[i["url"] for i in p.get("images", [])],
            floor_plans=[i["url"] for i in p.get("floor_plans", [])],
            multimedia={"captions": {i["url"]: i["caption"] for i in p.get("images", []) + p.get("floor_plans", [])},
                        "media_source": (p.get("sources") or [{}])[0].get("url"),
                        "media_credit": f"Images: {p['name']} official website ({p['developer']})"},
        )
        if b is None:
            b = core.BigProject(name=p["name"], **fields)
            core.big_projects_db.append(b)
        else:
            for k, v in fields.items():
                setattr(b, k, v)
            b.updated_at = datetime.now()
        stats["projects"] += 1

        existing = {x.project_unit: x for x in core.properties_db if x.project_id == b.id}
        live = set()
        for u in units:
            live.add(u["unit"])
            title = f"{p['name']} — {_unit_label(u)} {u['unit']} · {u['floor_label']}"
            values = dict(
                title=title, description=_description(p, u, checked), price=float(u["price"]),
                use_type="commercial" if u["kind"] in COMMERCIAL else "residential",
                category=KIND_CATEGORY.get(u["kind"], "apartment"), status="active",
                total_area=float(u["sqft"]), covered_area=float(u["sqft"]), marla_area=None, kanal_area=None,
                city_id=city.id, scheme_id=scheme.id if scheme else None,
                bedrooms=u.get("bedrooms") or None, floors=None, sector=p["name"], landmark=p.get("address"),
                street_address=p.get("address"), plot_number=u["unit"],
                latitude=loc["lat"], longitude=loc["lon"],
                amenities=[a for a in (u.get("facing"), "Private pool" if u["kind"] == "pool_apartment" else None,
                                       "Instalment plan", p.get("offer") and "Offer available") if a],
                project_id=b.id, project_unit=u["unit"], source_url=fields["website"],
                image_urls=[x for x in [*fields["image_urls"][:2], u.get("plan")] if x],
                floor_plans=[u["plan"]] if u.get("plan") else [],
            )
            prop = existing.get(u["unit"])
            if prop is None:
                prop = core.Property(**values)
                core.derive_areas(prop)
                core.properties_db.append(prop)
                stats["created"] += 1
            else:
                changed = any(getattr(prop, k) != v for k, v in values.items() if k not in ("marla_area", "kanal_area"))
                if changed:
                    for k, v in values.items():
                        setattr(prop, k, v)
                    core.derive_areas(prop)
                    prop.updated_at = datetime.now()
                    stats["updated"] += 1
        for code, prop in existing.items():
            if code not in live and prop.status == "active":
                prop.status = "sold"
                prop.updated_at = datetime.now()
                stats["sold"] += 1
    return stats


# ---------------------------------------------------------------- queries


def units(project_id: str, kind: Optional[str] = None, bedrooms: Optional[int] = None, max_price: Optional[float] = None,
          status: str = "active", limit: int = 500) -> Dict[str, Any]:
    core = _core()
    rows = [p for p in core.properties_db if p.project_id == project_id and (status == "all" or p.status == status)]
    if kind:
        rows = [p for p in rows if (p.category == kind or kind.lower() in p.title.lower())]
    if bedrooms is not None:
        rows = [p for p in rows if (p.bedrooms or 0) == bedrooms]
    if max_price:
        rows = [p for p in rows if p.price <= max_price]
    rows.sort(key=lambda p: p.price)
    return {"count": len(rows), "units": [{
        "id": p.id, "unit": p.project_unit, "title": p.title, "category": p.category, "use_type": p.use_type,
        "bedrooms": p.bedrooms, "sqft": p.total_area, "price": p.price, "status": p.status,
        "floor": p.title.split(" · ")[-1] if " · " in p.title else None,
    } for p in rows[:limit]]}


def as_megaprojects() -> List[Dict[str, Any]]:
    """The projects in the mega-projects format, for the infrastructure map layer."""
    out = []
    for p in load().get("projects", []):
        prices = [u["price"] for u in p.get("units", [])]
        n = len(p.get("units", []))
        plan = (p.get("payment_plan") or {}).get("summary")
        on_sale = (f" {n} units available" + (f" from {_money(min(prices))} to {_money(max(prices))}" if prices else "")
                   + (f"; {plan}" if plan else "") + ".") if n else ""
        out.append({
            "id": p["id"], "name": p["name"], "name_ur": None,
            "type": "mall" if p.get("project_type") == "mall" else "tower", "status": p["status"],
            "city": p["city"], "scheme": p.get("scheme"), "province": PROVINCE.get(p["city"]), "authority": p["developer"],
            "start_year": p.get("opened"),
            "completion": "Open" if p["status"] == "completed" else "To be confirmed by the developer",
            "summary": f"{p['tagline']} — {p['address']}." + on_sale,
            "impact": ("A landmark that draws shoppers and offices; homes and shops nearby are compared against it."
                       if p["status"] == "completed" else
                       "Adds new shops, offices and homes to the area; nearby rents and resale prices are compared "
                       "against its launch prices."),
            "uplift": "low", "impact_radius_km": 0.5,
            "geometry": {"type": "point", "center": [p["location"]["lat"], p["location"]["lon"]], "radius_km": 0.08},
            "sources": p.get("sources", []), "portal_project": True, "units_available": n,
            "price_from": min(prices) if prices else None, "website": (p.get("sources") or [{}])[0].get("url"),
            "image": (p.get("images") or [{}])[0].get("url"),
            "image_credit": (p.get("images") or [{}])[0].get("caption"),
        })
    return out
