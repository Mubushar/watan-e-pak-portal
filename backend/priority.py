"""
The portal's display order for cities and housing societies (Arz-e-Pak is based in Islamabad).

Cities
    Islamabad, Rawalpindi, Lahore, Karachi — then every other city by population.

Housing societies
    1. DHA Islamabad–Rawalpindi phases in this order: V, III, 4, VI, II, I
    2. Bahria Town (Rawalpindi / Islamabad) phases: 8, 7, then 4, 3, 2, 1
    3. Other DHA societies — the rest of DHA Islamabad–Rawalpindi first, then DHA in other
       cities in city order
    4. Islamabad's other popular societies
    5. Everything else across the country: by city order, then popularity (listings, size)

Listings and projects
    Follow the society order above (``place_key``): the DHA / Bahria phases first, then other DHA,
    then Islamabad, then the rest of the country by city order. Inside one society: featured, then
    newest listings.

Every list the portal shows (APIs, map, filters, admin forms) sorts with ``city_key`` /
``society_key`` / ``place_key`` so the order is the same everywhere. Change it here.
"""

from __future__ import annotations

import re
import sys
from typing import Any, Callable, Dict, Optional

CITY_FIRST = ["islamabad", "rawalpindi", "lahore", "karachi"]

# Exact society order for the first two groups (matched on normalised names).
DHA_IR_PHASES = ["dha phase v", "dha phase iii", "dha islamabad-rawalpindi phase 4", "dha phase vi", "dha phase ii", "dha phase i"]
BAHRIA_PHASES = ["bahria town phase 8", "bahria town phase 7", "bahria town phase 4", "bahria town phase 3",
                 "bahria town phase 2", "bahria town phase 1", "bahria town phases 1-6"]
DHA_IR_OTHERS = ["dha islamabad", "dha me-1 & me-2", "dha river view north", "dha river view south", "dha valley"]


def _norm(name: Optional[str]) -> str:
    n = (name or "").lower().replace("–", "-").replace("—", "-")
    n = re.sub(r"\s*\(.*?\)\s*", " ", n)  # "Bahria Town Phases 1-6 (Islamabad/Rawalpindi)"
    return re.sub(r"\s+", " ", n).strip()


def city_rank(name: Optional[str]) -> int:
    n = (name or "").strip().lower()
    return CITY_FIRST.index(n) if n in CITY_FIRST else len(CITY_FIRST)


def city_key(name: Optional[str], population: Optional[float] = None) -> tuple:
    return (city_rank(name), -(population or 0), (name or "").lower())


def society_key(name: Optional[str], city_name: Optional[str], city_population: Optional[float] = None,
                listings: int = 0, units: Optional[int] = None) -> tuple:
    n = _norm(name)
    popularity = (-listings, -(units or 0), n)
    if n in DHA_IR_PHASES:
        return (0, DHA_IR_PHASES.index(n), 0, ()) + popularity
    if n in BAHRIA_PHASES:
        return (1, BAHRIA_PHASES.index(n), 0, ()) + popularity
    city = city_key(city_name, city_population)
    if n.startswith("dha") or "defence housing" in n:
        return (2, 0 if n in DHA_IR_OTHERS else 1, DHA_IR_OTHERS.index(n) if n in DHA_IR_OTHERS else 0, city) + popularity
    if (city_name or "").strip().lower() == "islamabad":
        return (3, 0, 0, ()) + popularity
    return (4, 0, 0, city) + popularity


def place_key(scheme_name: Optional[str], city_name: Optional[str], city_population: Optional[float] = None,
              listings: int = 0, units: Optional[int] = None) -> tuple:
    """Order for anything that sits in a society, or only in a city (listings, projects).
    Without a society it ranks after the named societies of its city group."""
    if scheme_name:
        return society_key(scheme_name, city_name, city_population, listings, units)
    if (city_name or "").strip().lower() == "islamabad":
        return (3, 1, 0, (), 0, 0, "")
    return (4, 0, 0, city_key(city_name, city_population), 1, 0, "")


def _live_core() -> Any:
    """The loaded portal data module (``server``, or ``__main__`` when server.py runs directly)."""
    for name in ("server", "__main__"):
        mod = sys.modules.get(name)
        if mod is not None and hasattr(mod, "cities_db"):
            return mod
    return None


def city_population(name: Optional[str]) -> Optional[float]:
    core = _live_core()
    n = (name or "").strip().lower()
    for c in getattr(core, "cities_db", None) or []:
        if c.name.lower() == n:
            return c.population
    return None


def project_key(scheme_name: Optional[str], city_name: Optional[str]) -> tuple:
    """Order for project dicts that carry society and city names (mega projects)."""
    return place_key(scheme_name, city_name, city_population(city_name))


def listing_sort_key_for(core: Any) -> Callable[[Any], tuple]:
    """A key function for Property objects: society order, then featured, then newest."""
    cities: Dict[str, Any] = {c.id: c for c in core.cities_db}
    schemes: Dict[str, Any] = {s.id: s for s in core.housing_schemes_db}
    listings: Dict[str, int] = {}
    for p in core.properties_db:
        if p.scheme_id and p.status == "active":
            listings[p.scheme_id] = listings.get(p.scheme_id, 0) + 1

    def key(p: Any) -> tuple:
        c = cities.get(p.city_id)
        s = schemes.get(p.scheme_id) if p.scheme_id else None
        place = place_key(s.name if s else None, c.name if c else None, c.population if c else None,
                          listings.get(s.id, 0) if s else 0, s.total_units if s else None)
        return place + (not getattr(p, "featured", False), -(p.created_at.timestamp() if getattr(p, "created_at", None) else 0))

    return key


def big_project_sort_key_for(core: Any) -> Callable[[Any], tuple]:
    """A key function for BigProject objects (same order as listings)."""
    cities: Dict[str, Any] = {c.id: c for c in core.cities_db}
    schemes: Dict[str, Any] = {s.id: s for s in core.housing_schemes_db}

    def key(b: Any) -> tuple:
        c = cities.get(b.city_id)
        s = schemes.get(b.scheme_id) if b.scheme_id else None
        return place_key(s.name if s else None, c.name if c else None, c.population if c else None) + (b.name.lower(),)

    return key


def sort_cities(rows: list, name: str = "name", population: str = "population") -> list:
    """Sort dicts or objects with a city name and population."""
    get = (lambda r, k: r.get(k)) if rows and isinstance(rows[0], dict) else (lambda r, k: getattr(r, k, None))
    return sorted(rows, key=lambda r: city_key(get(r, name), get(r, population)))


def society_sort_key_for(core: Any) -> Any:
    """A key function for HousingScheme objects using the live data (city, listings, units)."""
    cities: Dict[str, Any] = {c.id: c for c in core.cities_db}
    listings: Dict[str, int] = {}
    for p in core.properties_db:
        if p.scheme_id and p.status == "active":
            listings[p.scheme_id] = listings.get(p.scheme_id, 0) + 1

    def key(s: Any) -> tuple:
        c = cities.get(s.city_id)
        return society_key(s.name, c.name if c else None, c.population if c else None, listings.get(s.id, 0), s.total_units)

    return key
