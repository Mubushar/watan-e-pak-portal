"""
Maintenance intelligence wing for the Real Estate Portal
=======================================================

A self-contained, framework-free knowledge + estimator engine for the
*maintenance* side of real estate.  It carries:

* **Asset components** — the maintainable parts of a building (structure,
  envelope, plumbing, electrical, HVAC, finishes, lifts, external works) with
  expected service life, replacement cost, criticality and periodic tasks.
* **Services & trades** — the maintenance services a portal lists, with unit
  costs, response times and emergency flags.
* **Defect catalogue** — symptoms, causes, severity, diagnosis, repair method,
  cost band, urgency and prevention for the defects Pakistani buildings
  actually suffer (seepage, cracks, dampness, corrosion, electrical faults …).
* **Intelligence** — a preventive-maintenance schedule, condition assessment,
  annual-maintenance-cost estimation, a multi-year lifecycle / reserve plan,
  repair-vs-replace analysis and repair-cost estimation.
* **Impact on real estate** — how maintenance and condition move market value,
  rent, yield, occupancy and tenant retention.
* **Guidelines** — maintenance best practice, statutory inspections, health &
  safety, and warranty terms.

No MCP or FastAPI code lives here: ``server.py`` exposes these functions over MCP
and ``api.py`` reuses the very same functions over REST.  ``gis.py`` renders the
plain dicts this module returns into themed, bilingual HTML pages.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# ============================================================
# CONFIGURATION
# ============================================================

MAINTENANCE_CONFIG: Dict[str, Any] = {
    "currency": "PKR",
    "currency_symbol": "Rs",
    "default_property_type": "house",
    "default_tier": "standard",
    "default_city": "Lahore",
    "inflation_cagr": 0.07,
    "age_factor_pct_per_year": 2.0,     # extra cost per year beyond the grace age
    "age_grace_years": 5,
    "age_factor_cap": 1.6,
    "default_build_rate_sqft": 4600.0,  # standard construction rate, for reserves
    "city_multipliers": {
        "Lahore": 1.00, "Karachi": 1.06, "Islamabad": 1.08, "Rawalpindi": 1.02,
        "Faisalabad": 0.97, "Multan": 0.95, "Peshawar": 0.98, "Quetta": 0.96,
    },
}

# annual routine-maintenance rate (PKR / sq-ft / year) by property type & standard
PROPERTY_MAINTENANCE_RATES: Dict[str, Dict[str, float]] = {
    "house":     {"basic": 14.0, "standard": 24.0, "premium": 40.0},
    "floor":     {"basic": 16.0, "standard": 28.0, "premium": 45.0},
    "apartment": {"basic": 20.0, "standard": 34.0, "premium": 55.0},
    "building":  {"basic": 24.0, "standard": 40.0, "premium": 62.0},
    "office":    {"basic": 28.0, "standard": 46.0, "premium": 72.0},
    "shop":      {"basic": 22.0, "standard": 38.0, "premium": 58.0},
    "space":     {"basic": 18.0, "standard": 30.0, "premium": 48.0},
    "warehouse": {"basic": 8.0,  "standard": 14.0, "premium": 22.0},
    "shed":      {"basic": 6.0,  "standard": 11.0, "premium": 18.0},
}

# AMC tier -> multiplier + what it includes
MAINTENANCE_TIERS: Dict[str, Dict[str, Any]] = {
    "basic": {"label": "Basic (on-call)", "multiplier": 1.0,
              "includes": ["Breakdown response", "Two preventive visits / year", "Phone support"]},
    "standard": {"label": "Standard AMC", "multiplier": 1.3,
                 "includes": ["Scheduled preventive maintenance", "Priority response (24 h)",
                              "Consumables included", "Quarterly inspection"]},
    "comprehensive": {"label": "Comprehensive AMC", "multiplier": 1.7,
                      "includes": ["All labour + parts (wear items)", "4-hour emergency response",
                                   "Annual condition survey", "Remote monitoring", "Guaranteed uptime"]},
}

ASSET_CATEGORIES = ["structural", "envelope", "mep", "finishes", "vertical", "external", "safety"]

# component -> life (years), replacement cost as % of new build cost, criticality
ASSET_COMPONENTS: List[Dict[str, Any]] = [
    {"key": "structure", "name": "Structure (frame, slabs, columns)", "category": "structural",
     "service_life_years": 60, "replacement_pct": 0.15, "criticality": "critical",
     "frequency": "annual", "tasks": ["Inspect for cracks, spalling and settlement",
                                      "Check expansion joints and bearings"]},
    {"key": "roof_waterproofing", "name": "Roof & waterproofing", "category": "envelope",
     "service_life_years": 10, "replacement_pct": 0.03, "criticality": "high",
     "frequency": "biannual", "tasks": ["Clear drains and outlets", "Inspect membrane and upstands",
                                        "Ponding test after monsoon"]},
    {"key": "external_walls", "name": "External walls & plaster", "category": "envelope",
     "service_life_years": 20, "replacement_pct": 0.04, "criticality": "medium",
     "frequency": "annual", "tasks": ["Check for cracks, efflorescence and damp patches",
                                      "Repair plaster and seal joints"]},
    {"key": "dpc_damp", "name": "Damp-proof course & basement tanking", "category": "envelope",
     "service_life_years": 25, "replacement_pct": 0.03, "criticality": "high",
     "frequency": "annual", "tasks": ["Check rising damp at plinth", "Verify basement sump/pump"]},
    {"key": "plumbing", "name": "Plumbing & drainage", "category": "mep",
     "service_life_years": 25, "replacement_pct": 0.06, "criticality": "high",
     "frequency": "quarterly", "tasks": ["Check for leaks and low pressure", "Clean drains and traps",
                                         "Service water pumps"]},
    {"key": "water_tank_pump", "name": "Water tanks & pumps", "category": "mep",
     "service_life_years": 12, "replacement_pct": 0.02, "criticality": "high",
     "frequency": "quarterly", "tasks": ["Clean and disinfect tanks", "Service pump and float valve"]},
    {"key": "electrical", "name": "Electrical wiring & distribution", "category": "mep",
     "service_life_years": 30, "replacement_pct": 0.05, "criticality": "critical",
     "frequency": "annual", "tasks": ["Test earthing and RCD/trip", "Thermal-scan the DB",
                                      "Check for loose connections"]},
    {"key": "hvac", "name": "HVAC & ventilation", "category": "mep",
     "service_life_years": 15, "replacement_pct": 0.06, "criticality": "high",
     "frequency": "quarterly", "tasks": ["Clean filters and coils", "Service compressors",
                                         "Check refrigerant and ducts"]},
    {"key": "generator", "name": "Generator / backup power", "category": "mep",
     "service_life_years": 15, "replacement_pct": 0.02, "criticality": "medium",
     "frequency": "monthly", "tasks": ["Run-up test under load", "Change oil and filters"]},
    {"key": "solar", "name": "Solar PV & water heating", "category": "mep",
     "service_life_years": 25, "replacement_pct": 0.05, "criticality": "medium",
     "frequency": "quarterly", "tasks": ["Clean panels", "Check inverter and cabling"]},
    {"key": "interior_paint", "name": "Interior paint & finishes", "category": "finishes",
     "service_life_years": 5, "replacement_pct": 0.010, "criticality": "low",
     "frequency": "annual", "tasks": ["Touch up damp/peeling patches", "Repaint high-wear areas"]},
    {"key": "exterior_paint", "name": "Exterior paint", "category": "finishes",
     "service_life_years": 6, "replacement_pct": 0.015, "criticality": "medium",
     "frequency": "biannual", "tasks": ["Check fading, chalking and mould", "Repaint per cycle"]},
    {"key": "floor_finishes", "name": "Floor & wall finishes", "category": "finishes",
     "service_life_years": 20, "replacement_pct": 0.05, "criticality": "low",
     "frequency": "annual", "tasks": ["Replace cracked tiles", "Re-polish marble"]},
    {"key": "doors_windows", "name": "Doors, windows & joinery", "category": "finishes",
     "service_life_years": 25, "replacement_pct": 0.04, "criticality": "medium",
     "frequency": "annual", "tasks": ["Oil hinges and lubricate hardware", "Re-seal glazing"]},
    {"key": "lifts", "name": "Elevators / lifts", "category": "vertical",
     "service_life_years": 20, "replacement_pct": 0.05, "criticality": "high",
     "frequency": "monthly", "tasks": ["Statutory safety inspection", "Service machine and doors"]},
    {"key": "external_works", "name": "External works, boundary & paving", "category": "external",
     "service_life_years": 20, "replacement_pct": 0.02, "criticality": "low",
     "frequency": "annual", "tasks": ["Repair boundary wall and gates", "Re-level paving and drains"]},
    {"key": "landscaping", "name": "Landscaping & irrigation", "category": "external",
     "service_life_years": 10, "replacement_pct": 0.01, "criticality": "low",
     "frequency": "quarterly", "tasks": ["Prune and fertilise", "Service irrigation lines"]},
    {"key": "fire_safety", "name": "Fire detection & suppression", "category": "safety",
     "service_life_years": 15, "replacement_pct": 0.02, "criticality": "critical",
     "frequency": "quarterly", "tasks": ["Test alarms and detectors", "Inspect extinguishers and hoses"]},
    {"key": "security_systems", "name": "Security & access control", "category": "safety",
     "service_life_years": 10, "replacement_pct": 0.01, "criticality": "medium",
     "frequency": "quarterly", "tasks": ["Test CCTV and access readers", "Update firmware/credentials"]},
]


def components(category: Optional[str] = None) -> List[Dict[str, Any]]:
    rows = list(ASSET_COMPONENTS)
    if category:
        rows = [c for c in rows if c["category"] == category]
    return rows


def find_component(key: Optional[str]) -> Optional[Dict[str, Any]]:
    if not key:
        return None
    k = str(key).strip().lower()
    return next((c for c in ASSET_COMPONENTS if c["key"] == k), None)


# ---- Services & trades -----------------------------------------------------

MAINTENANCE_SERVICES: List[Dict[str, Any]] = [
    {"key": "plumber_visit", "name": "Plumber — visit & minor repair", "category": "plumbing",
     "unit": "visit", "cost_low": 2500, "cost_high": 6000, "emergency": True, "response_hours": 4},
    {"key": "leak_repair", "name": "Water leak detection & repair", "category": "plumbing",
     "unit": "job", "cost_low": 3000, "cost_high": 15000, "emergency": True, "response_hours": 4},
    {"key": "drain_cleaning", "name": "Drain / sewer cleaning", "category": "plumbing",
     "unit": "job", "cost_low": 2500, "cost_high": 12000, "emergency": True, "response_hours": 6},
    {"key": "electrician_visit", "name": "Electrician — visit & repair", "category": "electrical",
     "unit": "visit", "cost_low": 3000, "cost_high": 8000, "emergency": True, "response_hours": 3},
    {"key": "wiring_rewire", "name": "Rewiring / DB upgrade", "category": "electrical",
     "unit": "point", "cost_low": 1800, "cost_high": 4500, "emergency": False, "response_hours": 24},
    {"key": "ac_service", "name": "AC / HVAC service", "category": "hvac",
     "unit": "unit", "cost_low": 4000, "cost_high": 9000, "emergency": False, "response_hours": 24},
    {"key": "painting", "name": "Painting (interior/exterior)", "category": "finishes",
     "unit": "sqft", "cost_low": 45, "cost_high": 120, "emergency": False, "response_hours": 72},
    {"key": "waterproofing", "name": "Waterproofing treatment", "category": "envelope",
     "unit": "sqft", "cost_low": 90, "cost_high": 260, "emergency": False, "response_hours": 72},
    {"key": "seepage_treatment", "name": "Seepage & dampness treatment", "category": "envelope",
     "unit": "sqft", "cost_low": 150, "cost_high": 450, "emergency": False, "response_hours": 48},
    {"key": "roof_repair", "name": "Roof repair", "category": "envelope",
     "unit": "sqft", "cost_low": 120, "cost_high": 400, "emergency": True, "response_hours": 12},
    {"key": "plaster_repair", "name": "Plaster / masonry repair", "category": "structural",
     "unit": "sqft", "cost_low": 180, "cost_high": 450, "emergency": False, "response_hours": 48},
    {"key": "tile_replace", "name": "Tile / marble replacement", "category": "finishes",
     "unit": "sqft", "cost_low": 250, "cost_high": 700, "emergency": False, "response_hours": 48},
    {"key": "pest_control", "name": "Pest / termite control", "category": "external",
     "unit": "job", "cost_low": 6000, "cost_high": 90000, "emergency": False, "response_hours": 48},
    {"key": "deep_cleaning", "name": "Deep cleaning", "category": "housekeeping",
     "unit": "sqft", "cost_low": 25, "cost_high": 60, "emergency": False, "response_hours": 24},
    {"key": "lift_amc", "name": "Lift AMC & service", "category": "vertical",
     "unit": "month", "cost_low": 25000, "cost_high": 90000, "emergency": True, "response_hours": 4},
    {"key": "generator_service", "name": "Generator service", "category": "mep",
     "unit": "service", "cost_low": 15000, "cost_high": 40000, "emergency": False, "response_hours": 24},
    {"key": "solar_service", "name": "Solar system service", "category": "mep",
     "unit": "service", "cost_low": 8000, "cost_high": 25000, "emergency": False, "response_hours": 48},
    {"key": "fire_service", "name": "Fire system inspection", "category": "safety",
     "unit": "service", "cost_low": 12000, "cost_high": 45000, "emergency": False, "response_hours": 24},
]


def services(category: Optional[str] = None, emergency: Optional[bool] = None) -> List[Dict[str, Any]]:
    rows = list(MAINTENANCE_SERVICES)
    if category:
        rows = [s for s in rows if s["category"] == category]
    if emergency is not None:
        rows = [s for s in rows if s["emergency"] == emergency]
    return rows


def find_service(key: Optional[str]) -> Optional[Dict[str, Any]]:
    if not key:
        return None
    k = str(key).strip().lower()
    return next((s for s in MAINTENANCE_SERVICES if s["key"] == k), None)


# ---- Defect catalogue ------------------------------------------------------

DEFECT_CATALOGUE: List[Dict[str, Any]] = [
    {"key": "hairline_cracks", "name": "Hairline plaster cracks", "category": "structural",
     "severity": "low", "urgency": "routine",
     "symptoms": ["Fine surface cracks on walls and ceilings"],
     "causes": ["Shrinkage of plaster", "Thermal movement", "Poor curing"],
     "affected_components": ["external_walls", "interior_paint"],
     "diagnosis": "Measure width and monitor; non-structural if < 1 mm",
     "repair": "Fill with filler/putty and repaint; treat as cosmetic",
     "unit": "sqft", "cost_low": 60, "cost_high": 180,
     "prevention": "Use correct mix and cure plaster properly."},
    {"key": "structural_cracks", "name": "Structural cracks", "category": "structural",
     "severity": "high", "urgency": "urgent",
     "symptoms": ["Wide (>2 mm) cracks", "Diagonal cracks at corners", "Cracks in beams/columns"],
     "causes": ["Settlement", "Overloading", "Seismic movement", "Inadequate reinforcement"],
     "affected_components": ["structure", "external_walls"],
     "diagnosis": "Structural engineer inspection; crack gauges; check foundations",
     "repair": "Grouting, jacketing or underpinning per engineer's design",
     "unit": "job", "cost_low": 150000, "cost_high": 1200000,
     "prevention": "Design to soil bearing capacity; provide ties and shear walls."},
    {"key": "roof_seepage", "name": "Roof seepage / leakage", "category": "envelope",
     "severity": "high", "urgency": "urgent",
     "symptoms": ["Damp patches on ceiling", "Dripping after rain", "Paint peeling on ceiling"],
     "causes": ["Failed waterproofing membrane", "Blocked outlets", "Poor slope"],
     "affected_components": ["roof_waterproofing", "interior_paint"],
     "diagnosis": "Ponding test; inspect membrane and upstands",
     "repair": "Re-lay membrane over prepared surface; correct slope and outlets",
     "unit": "sqft", "cost_low": 120, "cost_high": 400,
     "prevention": "Biannual cleaning and 5-yearly membrane renewal."},
    {"key": "water_seepage_wall", "name": "Wall seepage & dampness", "category": "envelope",
     "severity": "medium", "urgency": "soon",
     "symptoms": ["Damp patches on walls", "Musty smell", "Mould near skirting"],
     "causes": ["Failed plumbing behind wall", "Rain penetration", "Rising damp"],
     "affected_components": ["external_walls", "dpc_damp", "plumbing"],
     "diagnosis": "Locate source (plumbing vs external); moisture-meter scan",
     "repair": "Rectify source, inject DPC / re-plaster with waterproof additive",
     "unit": "sqft", "cost_low": 150, "cost_high": 450,
     "prevention": "Maintain external sealant and plumbing; proper DPC."},
    {"key": "efflorescence", "name": "Efflorescence (salt deposits)", "category": "envelope",
     "severity": "low", "urgency": "routine",
     "symptoms": ["White powdery deposits on masonry", "Paint flaking"],
     "causes": ["Soluble salts in bricks/mortar", "Continuous moisture"],
     "affected_components": ["external_walls"],
     "diagnosis": "Visual; rule out active water source",
     "repair": "Dry-brush, wash, apply salt-resistant sealer",
     "unit": "sqft", "cost_low": 80, "cost_high": 220,
     "prevention": "Use quality bricks and damp-proofing."},
    {"key": "rebar_corrosion", "name": "Concrete spalling & rebar corrosion", "category": "structural",
     "severity": "high", "urgency": "soon",
     "symptoms": ["Concrete falling off", "Rust stains", "Exposed corroding rebar"],
     "causes": ["Inadequate cover", "Water/chloride ingress", "Carbonation"],
     "affected_components": ["structure"],
     "diagnosis": "Tap-test and cover-meter; assess extent",
     "repair": "Remove loose concrete, treat rebar, patch with repair mortar, protective coating",
     "unit": "sqft", "cost_low": 400, "cost_high": 1200,
     "prevention": "Correct cover, waterproofing and timely patch repair."},
    {"key": "plumbing_leak", "name": "Plumbing leakage", "category": "mep",
     "severity": "medium", "urgency": "urgent",
     "symptoms": ["Low pressure", "Wet patches", "High water bill", "Dripping fittings"],
     "causes": ["Corroded GI pipes", "Loose joints", "High pressure"],
     "affected_components": ["plumbing", "water_tank_pump"],
     "diagnosis": "Pressure test; isolate sections",
     "repair": "Replace affected pipe run / fittings; pressure-test after",
     "unit": "job", "cost_low": 3000, "cost_high": 15000,
     "prevention": "Replace aging GI with PPRC; install pressure regulator."},
    {"key": "blocked_drain", "name": "Blocked drains / sewer", "category": "mep",
     "severity": "medium", "urgency": "urgent",
     "symptoms": ["Slow drainage", "Foul smell", "Overflow at traps"],
     "causes": ["Grease/solids build-up", "Root intrusion", "Poor slope"],
     "affected_components": ["plumbing"],
     "diagnosis": "CCTV drain survey / rodding",
     "repair": "High-pressure jetting; repair damaged line",
     "unit": "job", "cost_low": 2500, "cost_high": 12000,
     "prevention": "Periodic cleaning and grease traps."},
    {"key": "electrical_fault", "name": "Electrical fault / overheating", "category": "mep",
     "severity": "high", "urgency": "urgent",
     "symptoms": ["Tripping breakers", "Hot sockets", "Burning smell", "Flickering"],
     "causes": ["Loose connections", "Overload", "Insulation failure", "Poor earthing"],
     "affected_components": ["electrical"],
     "diagnosis": "Thermal scan; earth-resistance and RCD tests",
     "repair": "Tighten/replace connections, upgrade MCBs/DB, restore earthing",
     "unit": "job", "cost_low": 5000, "cost_high": 60000,
     "prevention": "Load balancing and periodic thermal scanning."},
    {"key": "hvac_underperform", "name": "HVAC underperformance", "category": "mep",
     "severity": "low", "urgency": "soon",
     "symptoms": ["Weak cooling", "Noisy unit", "High power use", "Water dripping"],
     "causes": ["Dirty filters/coils", "Low refrigerant", "Blocked drain"],
     "affected_components": ["hvac"],
     "diagnosis": "Measure superheat/delta-T; inspect coils and drain",
     "repair": "Clean, re-gas, clear drain; service compressor",
     "unit": "unit", "cost_low": 4000, "cost_high": 9000,
     "prevention": "Quarterly filter cleaning and annual service."},
    {"key": "paint_peeling", "name": "Paint peeling / chalking", "category": "finishes",
     "severity": "low", "urgency": "routine",
     "symptoms": ["Flaking paint", "Powdery surface", "Faded colour"],
     "causes": ["Moisture behind film", "Poor surface prep", "Ageing"],
     "affected_components": ["interior_paint", "exterior_paint"],
     "diagnosis": "Check for underlying dampness",
     "repair": "Rectify moisture, remove loose film, prime and repaint",
     "unit": "sqft", "cost_low": 55, "cost_high": 150,
     "prevention": "Fix moisture sources; repaint on schedule."},
    {"key": "tile_debond", "name": "Tile debonding / hollow tiles", "category": "finishes",
     "severity": "low", "urgency": "soon",
     "symptoms": ["Hollow sound", "Loose tiles", "Cracked joints"],
     "causes": ["Poor adhesive coverage", "Movement", "Water ingress"],
     "affected_components": ["floor_finishes"],
     "diagnosis": "Tap-test for hollow areas",
     "repair": "Remove and re-fix affected tiles with proper adhesive",
     "unit": "sqft", "cost_low": 250, "cost_high": 700,
     "prevention": "Full-bed fixing and expansion joints."},
    {"key": "tank_contamination", "name": "Water tank contamination", "category": "mep",
     "severity": "medium", "urgency": "soon",
     "symptoms": ["Discoloured water", "Odour", "Sediment"],
     "causes": ["No cleaning", "Open/cracked tank", "Rodent ingress"],
     "affected_components": ["water_tank_pump"],
     "diagnosis": "Visual + water test",
     "repair": "Drain, scrub, disinfect and seal tank",
     "unit": "tank", "cost_low": 8000, "cost_high": 30000,
     "prevention": "Clean and disinfect twice a year; keep tank sealed."},
    {"key": "termite", "name": "Termite / wood borer attack", "category": "external",
     "severity": "high", "urgency": "soon",
     "symptoms": ["Hollow wooden doors", "Mud tubes", "Frass"],
     "causes": ["Untreated timber", "Moisture", "Soil contact"],
     "affected_components": ["doors_windows", "structure"],
     "diagnosis": "Inspection of timber and foundations",
     "repair": "Chemical barrier treatment; replace affected timber",
     "unit": "job", "cost_low": 20000, "cost_high": 90000,
     "prevention": "Pre-construction anti-termite treatment; keep wood dry."},
    {"key": "lift_fault", "name": "Lift malfunction", "category": "vertical",
     "severity": "high", "urgency": "urgent",
     "symptoms": ["Door jams", "Leveling errors", "Stopping between floors"],
     "causes": ["Worn door mechanism", "Controller fault", "Missed servicing"],
     "affected_components": ["lifts"],
     "diagnosis": "Controller diagnostics + door mechanism inspection",
     "repair": "Service/replace parts; safety re-certification",
     "unit": "job", "cost_low": 15000, "cost_high": 250000,
     "prevention": "Monthly AMC and statutory annual inspection."},
]


def defects(category: Optional[str] = None, severity: Optional[str] = None,
            component: Optional[str] = None) -> List[Dict[str, Any]]:
    rows = list(DEFECT_CATALOGUE)
    if category:
        rows = [d for d in rows if d["category"] == category]
    if severity:
        rows = [d for d in rows if d["severity"] == severity]
    if component:
        rows = [d for d in rows if component in d["affected_components"]]
    return rows


def find_defect(key: Optional[str]) -> Optional[Dict[str, Any]]:
    if not key:
        return None
    k = str(key).strip().lower()
    return next((d for d in DEFECT_CATALOGUE if d["key"] == k), None)


# ---- Condition, guidelines, warranty, inspection ---------------------------

CONDITION_SCALE: List[Dict[str, Any]] = [
    {"rating": 5, "label": "Excellent (new / near-new)", "band": "excellent", "action": "Preventive maintenance only"},
    {"rating": 4, "label": "Good (well maintained)", "band": "good", "action": "Routine preventive maintenance"},
    {"rating": 3, "label": "Fair (some defects)", "band": "fair", "action": "Planned repairs within the year"},
    {"rating": 2, "label": "Poor (significant defects)", "band": "poor", "action": "Major repairs / partial replacement"},
    {"rating": 1, "label": "Critical (deteriorated)", "band": "critical", "action": "Component replacement / structural review"},
]

MAINTENANCE_GUIDELINES: List[Dict[str, Any]] = [
    {"key": "preventive_first", "title": "Preventive over reactive", "category": "best_practice",
     "summary": "A planned preventive schedule costs far less over a building's life than breakdown repairs.",
     "rules": ["Follow the component frequency table", "Keep a maintenance log for every asset",
               "Act on defects while they are minor"]},
    {"key": "water_waterproofing", "title": "Water is the enemy", "category": "best_practice",
     "summary": "Most structural and finish deterioration starts with uncontrolled water.",
     "rules": ["Clean roof drains before and after monsoon", "Re-waterproof on schedule",
               "Fix plumbing leaks immediately"]},
    {"key": "statutory", "title": "Statutory inspections", "category": "compliance",
     "summary": "Some systems legally require periodic third-party inspection.",
     "rules": ["Lift safety inspection every 6–12 months",
               "Fire system inspection and extinguisher servicing",
               "Electrical earthing/load inspection for commercial occupancy"]},
    {"key": "amc", "title": "Annual maintenance contracts", "category": "management",
     "summary": "AMCs lock in response times and cost certainty for critical systems.",
     "rules": ["Cover lifts, HVAC, generator, solar and fire",
               "Define response SLAs and included parts", "Review AMC scope annually"]},
    {"key": "reserve_fund", "title": "Plan a reserve / sinking fund", "category": "finance",
     "summary": "Buildings age; a funded reserve prevents surprise capital shocks.",
     "rules": ["Accumulate the lifecycle reserve every year",
               "Recalculate the reserve study every 3–5 years",
               "Separate capital replacement from routine maintenance"]},
    {"key": "hse_maintenance", "title": "Safety during maintenance", "category": "safety",
     "summary": "Repair works carry their own hazards.",
     "rules": ["Permit-to-work for height, electrical and confined spaces",
               "Isolate power before electrical work", "PPE and safe access at all times"]},
    {"key": "documentation", "title": "Documentation & handover", "category": "management",
     "summary": "As-built drawings, warranties and manuals are essential for future maintenance.",
     "rules": ["Keep as-built drawings and O&M manuals",
               "Record warranty start/end dates", "Log all repairs with cost and contractor"]},
    {"key": "tenant_comms", "title": "Communication with occupants", "category": "management",
     "summary": "Clear communication keeps satisfaction and retention high.",
     "rules": ["Publish the maintenance calendar", "Give notice before shutdowns",
               "Provide a single service-request channel"]},
]

WARRANTY_TERMS: Dict[str, Dict[str, Any]] = {
    "structure": {"years": 10, "covers": "Structural defects and workmanship", "excludes": "Misuse, alterations, disasters"},
    "roof_waterproofing": {"years": 5, "covers": "Waterproofing system performance", "excludes": "Blocked drains, subsequent penetrations"},
    "plumbing": {"years": 2, "covers": "Installation and fittings", "excludes": "Wear items, freezing, pressure abuse"},
    "electrical": {"years": 2, "covers": "Wiring and installation", "excludes": "Overload, unauthorised modifications"},
    "hvac": {"years": 1, "covers": "Manufacturer + installation", "excludes": "Consumables, cleaning"},
    "paint": {"years": 1, "covers": "Coating defects", "excludes": "Substrate moisture, surface damage"},
    "lifts": {"years": 2, "covers": "Manufacturer + installation", "excludes": "Wear parts, misuse"},
}

INSPECTION_CHECKLIST: Dict[str, List[str]] = {
    "structural": ["Cracks, spalling, exposed rebar", "Settlement or deflection", "Expansion joints",
                   "Subsidence around foundations"],
    "envelope": ["Roof membrane and outlets", "Damp patches and efflorescence", "External sealants",
                 "Basement tanking / sump"],
    "mep": ["Water pressure and leaks", "Drainage flow", "Earthing and RCD trip test",
            "HVAC filters and refrigerant", "Generator run test"],
    "finishes": ["Paint condition", "Tile hollows and cracks", "Door/window operation and sealing"],
    "safety": ["Fire alarms and extinguishers", "Escape routes clear", "Lift safety certificate",
               "CCTV and access control"],
}


def guidelines(category: Optional[str] = None) -> List[Dict[str, Any]]:
    rows = list(MAINTENANCE_GUIDELINES)
    if category:
        rows = [g for g in rows if g["category"] == category]
    return rows


def warranty(component: Optional[str] = None) -> Dict[str, Any]:
    if component and component in WARRANTY_TERMS:
        return {"component": component, **WARRANTY_TERMS[component]}
    return {"terms": WARRANTY_TERMS}


def inspection_checklist(area: Optional[str] = None) -> Dict[str, Any]:
    if area and area in INSPECTION_CHECKLIST:
        return {"area": area, "checks": INSPECTION_CHECKLIST[area]}
    return {"areas": INSPECTION_CHECKLIST}


# ============================================================
# MODELS & STORES (plans & work orders)
# ============================================================


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


def _m(model: BaseModel) -> Dict[str, Any]:
    return model.model_dump(mode="json")


class MaintenancePlan(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("mp_"))
    title: str
    property_type: str = "house"
    tier: str = "standard"
    city: str = "Lahore"
    covered_area_sqft: float
    age_years: float = 0.0
    annual_cost: float = 0.0
    annual_cost_per_sqft: float = 0.0
    reserve_per_year: float = 0.0
    condition_band: str = "good"
    notes: Optional[str] = None
    created_at: str = Field(default_factory=_now)


class WorkOrder(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("wo_"))
    title: str
    property_type: str = "house"
    component: Optional[str] = None
    defect: Optional[str] = None
    priority: str = "routine"                 # routine | soon | urgent | emergency
    status: str = "open"                      # open | assigned | in_progress | done | cancelled
    description: Optional[str] = None
    estimated_cost: float = 0.0
    assignee: Optional[str] = None
    created_at: str = Field(default_factory=_now)


plans_db: List[MaintenancePlan] = []
work_orders_db: List[WorkOrder] = []


def find_plan(plan_id: Optional[str]) -> Optional[MaintenancePlan]:
    return next((p for p in plans_db if p.id == plan_id), None)


def find_work_order(wo_id: Optional[str]) -> Optional[WorkOrder]:
    return next((w for w in work_orders_db if w.id == wo_id), None)


def list_plans(property_type: Optional[str] = None) -> List[MaintenancePlan]:
    rows = list(plans_db)
    if property_type:
        rows = [p for p in rows if p.property_type == property_type]
    return sorted(rows, key=lambda p: p.created_at, reverse=True)


def list_work_orders(status: Optional[str] = None, priority: Optional[str] = None,
                     component: Optional[str] = None) -> List[WorkOrder]:
    rows = list(work_orders_db)
    if status:
        rows = [w for w in rows if w.status == status]
    if priority:
        rows = [w for w in rows if w.priority == priority]
    if component:
        rows = [w for w in rows if w.component == component]
    return sorted(rows, key=lambda w: w.created_at, reverse=True)


# ============================================================
# INTELLIGENCE ENGINE
# ============================================================


def format_pkr(amount: float, symbol: str = "Rs") -> str:
    a = float(amount or 0.0)
    if abs(a) >= 1_000_000_000:
        return f"{symbol} {a / 1_000_000_000:,.2f}B"
    if abs(a) >= 1_000_000:
        return f"{symbol} {a / 1_000_000:,.2f}M"
    if abs(a) >= 1_000:
        return f"{symbol} {a / 1_000:,.1f}K"
    return f"{symbol} {a:,.0f}"


# category shares of routine annual maintenance
CATEGORY_SHARES: Dict[str, float] = {
    "plumbing": 18.0, "electrical": 15.0, "hvac": 12.0, "finishes": 12.0,
    "envelope": 10.0, "structural": 12.0, "vertical": 7.0, "external": 8.0,
    "safety": 6.0,
}


def _age_factor(age_years: float) -> float:
    cfg = MAINTENANCE_CONFIG
    extra = cfg["age_factor_pct_per_year"] / 100.0 * max(0.0, age_years - cfg["age_grace_years"])
    return min(cfg["age_factor_cap"], 1.0 + extra)


def estimate_maintenance(
    covered_area: float, property_type: str = "house", tier: str = "standard",
    quality: str = "standard", age_years: float = 0.0, city: Optional[str] = None,
    floors: int = 1,
) -> Dict[str, Any]:
    """Annual routine-maintenance cost estimate with a category breakdown."""
    cfg = MAINTENANCE_CONFIG
    if property_type not in PROPERTY_MAINTENANCE_RATES:
        return {"error": f"Unknown property_type: {property_type}",
                "types": sorted(PROPERTY_MAINTENANCE_RATES)}
    if tier not in MAINTENANCE_TIERS:
        return {"error": f"Unknown tier: {tier}", "tiers": sorted(MAINTENANCE_TIERS)}
    if covered_area <= 0:
        return {"error": "covered_area must be > 0"}

    city_name = city or cfg["default_city"]
    city_factor = cfg["city_multipliers"].get(city_name, 1.0)
    quality_key = "premium" if quality in ("premium", "luxury") else ("basic" if quality == "economy" else "standard")
    base_rate = PROPERTY_MAINTENANCE_RATES[property_type][quality_key]
    tier_mult = MAINTENANCE_TIERS[tier]["multiplier"]
    age_factor = _age_factor(age_years)

    rate = base_rate * city_factor * tier_mult * age_factor
    annual = covered_area * rate

    shares = dict(CATEGORY_SHARES)
    if property_type in ("house", "floor", "shop", "space", "warehouse", "shed"):
        shares.pop("vertical", None)
    total_share = sum(shares.values())
    breakdown = []
    for cat, share in sorted(shares.items(), key=lambda kv: -kv[1]):
        amount = annual * share / total_share
        breakdown.append({"category": cat, "share_pct": round(share / total_share * 100, 1),
                          "annual_cost": round(amount, 0)})

    reserve = lifecycle_reserve(covered_area, property_type, quality, age_years, city=city_name)
    matched = services()
    return {
        "inputs": {"covered_area_sqft": covered_area, "property_type": property_type, "tier": tier,
                   "quality": quality, "age_years": age_years, "city": city_name, "floors": floors},
        "assumptions": {"base_rate_sqft_year": base_rate, "city_factor": city_factor,
                        "tier_multiplier": tier_mult, "age_factor": round(age_factor, 3),
                        "effective_rate_sqft_year": round(rate, 2)},
        "annual": {
            "total": round(annual, 0), "per_sqft_year": round(rate, 2),
            "monthly": round(annual / 12.0, 0),
            "total_text": format_pkr(annual), "monthly_text": f"Rs {annual / 12.0:,.0f} / month",
        },
        "category_breakdown": breakdown,
        "reserve": reserve,
        "tier_info": MAINTENANCE_TIERS[tier],
        "services_sample": [{"key": s["key"], "name": s["name"], "unit": s["unit"],
                             "cost_low": s["cost_low"], "cost_high": s["cost_high"]} for s in matched[:6]],
    }


def lifecycle_reserve(covered_area: float, property_type: str = "house", quality: str = "standard",
                      age_years: float = 0.0, city: Optional[str] = None) -> Dict[str, Any]:
    """Annual sinking-fund contribution to replace components at end of life."""
    cfg = MAINTENANCE_CONFIG
    quality_mult = {"economy": 0.9, "standard": 1.0, "premium": 1.2, "luxury": 1.4}.get(quality, 1.0)
    city_factor = cfg["city_multipliers"].get(city or cfg["default_city"], 1.0)
    build_value = covered_area * cfg["default_build_rate_sqft"] * quality_mult * city_factor
    include_lifts = property_type in ("apartment", "building", "office")
    rows = []
    annual_total = 0.0
    for c in ASSET_COMPONENTS:
        if c["key"] == "lifts" and not include_lifts:
            continue
        replacement_cost = build_value * c["replacement_pct"]
        annual = replacement_cost / c["service_life_years"]
        annual_total += annual
        rows.append({"component": c["key"], "name": c["name"],
                     "service_life_years": c["service_life_years"],
                     "replacement_cost": round(replacement_cost, 0),
                     "annual_reserve": round(annual, 0)})
    rows.sort(key=lambda r: -r["annual_reserve"])
    return {"build_value": round(build_value, 0), "annual_reserve": round(annual_total, 0),
            "annual_reserve_per_sqft": round(annual_total / covered_area, 2) if covered_area else 0.0,
            "monthly_reserve": round(annual_total / 12.0, 0),
            "components": rows,
            "note": "Full component-replacement reserve; separate from routine maintenance."}


def lifecycle_plan(covered_area: float, property_type: str = "house", quality: str = "standard",
                   age_years: float = 0.0, city: Optional[str] = None, years: int = 30) -> Dict[str, Any]:
    """Multi-year capital-replacement schedule (a reserve study)."""
    cfg = MAINTENANCE_CONFIG
    quality_mult = {"economy": 0.9, "standard": 1.0, "premium": 1.2, "luxury": 1.4}.get(quality, 1.0)
    city_factor = cfg["city_multipliers"].get(city or cfg["default_city"], 1.0)
    build_value = covered_area * cfg["default_build_rate_sqft"] * quality_mult * city_factor
    include_lifts = property_type in ("apartment", "building", "office")
    infl = cfg["inflation_cagr"]

    schedule: Dict[int, List[Dict[str, Any]]] = {}
    rows = []
    for c in ASSET_COMPONENTS:
        if c["key"] == "lifts" and not include_lifts:
            continue
        life = c["service_life_years"]
        cost = build_value * c["replacement_pct"]
        # first replacement: remaining life after the building's current age
        first = life - (age_years % life) if age_years > 0 else float(life)
        t = first
        while t <= years:
            year = int(round(t))
            inflated = cost * ((1 + infl) ** year)
            schedule.setdefault(year, []).append({"component": c["key"], "name": c["name"],
                                                  "cost": round(inflated, 0)})
            rows.append({"year": year, "component": c["key"], "name": c["name"], "cost": round(inflated, 0)})
            t += life
    rows.sort(key=lambda r: (r["year"], -r["cost"]))
    yearly = [{"year": y, "items": items,
               "total": round(sum(i["cost"] for i in items), 0)} for y, items in sorted(schedule.items())]
    total = sum(r["cost"] for r in rows)
    return {"covered_area_sqft": covered_area, "property_type": property_type, "quality": quality,
            "age_years": age_years, "horizon_years": years, "build_value": round(build_value, 0),
            "total_replacement_cost": round(total, 0),
            "annualised": round(total / years, 0) if years else 0.0,
            "replacements": rows, "by_year": yearly,
            "note": "Costs inflated at the configured rate from today's values."}


def preventive_schedule(property_type: str = "house", age_years: float = 0.0,
                        horizon_months: int = 12) -> Dict[str, Any]:
    """A periodic preventive-maintenance calendar for a property."""
    include_lifts = property_type in ("apartment", "building", "office")
    period_months = {"monthly": 1, "quarterly": 3, "biannual": 6, "annual": 12}
    tasks = []
    for c in ASSET_COMPONENTS:
        if c["key"] == "lifts" and not include_lifts:
            continue
        step = period_months.get(c["frequency"], 12)
        for month in range(step, horizon_months + 1, step):
            tasks.append({"month": month, "component": c["key"], "name": c["name"],
                          "category": c["category"], "frequency": c["frequency"],
                          "criticality": c["criticality"], "tasks": c["tasks"]})
    tasks.sort(key=lambda t: (t["month"], t["component"]))
    by_month = {}
    for t in tasks:
        by_month.setdefault(t["month"], []).append(t["name"])
    return {"property_type": property_type, "age_years": age_years,
            "horizon_months": horizon_months, "task_count": len(tasks),
            "by_month": {str(m): names for m, names in sorted(by_month.items())},
            "tasks": tasks}


def condition_assessment(age_years: float, ratings: Optional[Dict[str, int]] = None,
                         property_type: str = "house") -> Dict[str, Any]:
    """Score a building's condition (1–5) into a band with recommended actions."""
    cats = ["structural", "envelope", "mep", "finishes", "safety"]
    if ratings is None:
        # derive a default from age: newer = better, floors at ~25 years old
        base = max(1.5, 5.0 - age_years / 8.0)
        ratings = {c: int(round(base)) for c in cats}
    ratings = {c: max(1, min(5, int(ratings.get(c, 3)))) for c in cats}
    score = round(sum(ratings.values()) / len(ratings), 2)
    band = next((s for s in CONDITION_SCALE if s["rating"] == int(round(score))), CONDITION_SCALE[-1])
    actions = []
    for c, r in ratings.items():
        for d in defects(category=c):
            if r <= 3 and d["severity"] in ("high", "medium"):
                actions.append({"component": c, "defect": d["key"], "urgency": d["urgency"],
                                "repair": d["repair"]})
    return {"property_type": property_type, "age_years": age_years, "ratings": ratings,
            "score": score, "band": band["band"], "band_label": band["label"],
            "recommended_action": band["action"], "actions": actions[:8],
            "scale": CONDITION_SCALE}


def repair_estimate(defect: str, quantity: float = 1.0, city: Optional[str] = None) -> Dict[str, Any]:
    """Cost estimate to repair a known defect over a given quantity."""
    d = find_defect(defect)
    if not d:
        return {"error": f"Unknown defect: {defect}", "defects": [x["key"] for x in DEFECT_CATALOGUE]}
    city_factor = MAINTENANCE_CONFIG["city_multipliers"].get(city or MAINTENANCE_CONFIG["default_city"], 1.0)
    low = d["cost_low"] * quantity * city_factor
    high = d["cost_high"] * quantity * city_factor
    mid = (low + high) / 2.0
    return {"defect": d["key"], "name": d["name"], "severity": d["severity"], "urgency": d["urgency"],
            "unit": d["unit"], "quantity": quantity, "city": city or MAINTENANCE_CONFIG["default_city"],
            "cost_low": round(low, 0), "cost_high": round(high, 0), "cost_mid": round(mid, 0),
            "cost_mid_text": format_pkr(mid),
            "repair_method": d["repair"], "prevention": d["prevention"]}


def repair_or_replace(component: str, age_years: float, condition: Optional[str] = None,
                      covered_area: float = 1000.0, quality: str = "standard",
                      city: Optional[str] = None) -> Dict[str, Any]:
    """Decide between repairing and replacing a component."""
    c = find_component(component)
    if not c:
        return {"error": f"Unknown component: {component}", "components": [x["key"] for x in ASSET_COMPONENTS]}
    cfg = MAINTENANCE_CONFIG
    quality_mult = {"economy": 0.9, "standard": 1.0, "premium": 1.2, "luxury": 1.4}.get(quality, 1.0)
    city_factor = cfg["city_multipliers"].get(city or cfg["default_city"], 1.0)
    build_value = covered_area * cfg["default_build_rate_sqft"] * quality_mult * city_factor
    replace_cost = build_value * c["replacement_pct"]
    repair_cost = replace_cost * 0.30                     # typical repair vs replace
    life = c["service_life_years"]
    used_ratio = min(1.5, age_years / life) if life else 1.0
    band = condition or ("critical" if used_ratio >= 1.0 else "poor" if used_ratio >= 0.75
                         else "fair" if used_ratio >= 0.5 else "good")
    replace = used_ratio >= 0.75 or band in ("poor", "critical")
    # 5-year cost comparison
    repair_5 = repair_cost * 2.2 if not replace else repair_cost * 3.5
    replace_5 = replace_cost
    return {
        "component": component, "name": c["name"], "age_years": age_years,
        "service_life_years": life, "life_used_pct": round(used_ratio * 100, 1),
        "condition": band, "decision": "replace" if replace else "repair",
        "repair_cost": round(repair_cost, 0), "replace_cost": round(replace_cost, 0),
        "repair_cost_text": format_pkr(repair_cost), "replace_cost_text": format_pkr(replace_cost),
        "five_year": {"repair_path": round(repair_5, 0), "replace_path": round(replace_5, 0)},
        "rationale": ("Near/past end of service life or poor condition — replacement is cheaper over 5 years."
                      if replace else "Component has remaining life — repair is the better value now."),
        "criticality": c["criticality"],
    }


def maintenance_impact(
    market_value: float, monthly_rent: float, covered_area: float = 1000.0,
    current_condition: str = "fair", tier: str = "standard",
) -> Dict[str, Any]:
    """How condition and maintenance move value, rent, yield and occupancy."""
    well = {"value_mult": 1.04, "rent_mult": 1.06, "occupancy": 0.94, "days_to_let": 25, "retention": 0.88}
    deferred = {"value_mult": 0.88, "rent_mult": 0.85, "occupancy": 0.76, "days_to_let": 70, "retention": 0.55}
    fair = {"value_mult": 0.97, "rent_mult": 0.96, "occupancy": 0.88, "days_to_let": 45, "retention": 0.72}
    state = {"well_maintained": well, "fair": fair, "deferred": deferred}.get(current_condition, fair)
    improved = well

    def _row(s: Dict[str, float]) -> Dict[str, Any]:
        val = market_value * s["value_mult"]
        rent = monthly_rent * s["rent_mult"]
        annual_rent = rent * 12 * s["occupancy"]
        return {"value": round(val, 0), "value_text": format_pkr(val),
                "monthly_rent": round(rent, 0), "occupancy_pct": round(s["occupancy"] * 100, 1),
                "annual_effective_rent": round(annual_rent, 0),
                "gross_yield_pct": round(annual_rent / val * 100, 2) if val else 0.0,
                "days_to_let": s["days_to_let"], "retention_pct": round(s["retention"] * 100, 1)}

    current = _row(state)
    good = _row(improved)
    uplift_value = good["value"] - current["value"]
    uplift_rent = good["annual_effective_rent"] - current["annual_effective_rent"]
    annual_cost = estimate_maintenance(covered_area, tier=tier).get("annual", {}).get("total", 0.0)
    net = uplift_rent - annual_cost
    return {
        "current_condition": current_condition, "tier": tier,
        "current": current, "well_maintained": good,
        "value_uplift": round(uplift_value, 0), "value_uplift_text": format_pkr(uplift_value),
        "annual_rent_uplift": round(uplift_rent, 0),
        "annual_maintenance_cost": round(annual_cost, 0),
        "net_annual_benefit": round(net, 0),
        "verdict": "maintenance pays" if net > 0 else "review scope",
        "note": "Well-maintained assets sell faster, let faster and retain tenants longer.",
    }


def maintenance_overview() -> Dict[str, Any]:
    """Counts and breakdowns for the whole maintenance wing."""
    def _tally(vals: Any) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for v in vals:
            out[v] = out.get(v, 0) + 1
        return out
    return {
        "config": MAINTENANCE_CONFIG,
        "counts": {
            "components": len(ASSET_COMPONENTS), "services": len(MAINTENANCE_SERVICES),
            "defects": len(DEFECT_CATALOGUE), "guidelines": len(MAINTENANCE_GUIDELINES),
            "warranty_terms": len(WARRANTY_TERMS), "inspection_areas": len(INSPECTION_CHECKLIST),
            "tiers": len(MAINTENANCE_TIERS), "saved_plans": len(plans_db),
            "work_orders": len(work_orders_db),
        },
        "components_by_category": _tally(c["category"] for c in ASSET_COMPONENTS),
        "services_by_category": _tally(s["category"] for s in MAINTENANCE_SERVICES),
        "defects_by_severity": _tally(d["severity"] for d in DEFECT_CATALOGUE),
        "property_types": sorted(PROPERTY_MAINTENANCE_RATES),
        "tiers": {k: v["label"] for k, v in MAINTENANCE_TIERS.items()},
        "condition_scale": CONDITION_SCALE,
        "cities": list(MAINTENANCE_CONFIG["city_multipliers"]),
    }


def save_plan(est: Dict[str, Any], title: str, notes: Optional[str] = None) -> MaintenancePlan:
    inp = est.get("inputs", {})
    rec = MaintenancePlan(
        title=title, property_type=inp.get("property_type", "house"),
        tier=inp.get("tier", "standard"), city=inp.get("city", MAINTENANCE_CONFIG["default_city"]),
        covered_area_sqft=inp.get("covered_area_sqft", 0.0), age_years=inp.get("age_years", 0.0),
        annual_cost=est.get("annual", {}).get("total", 0.0),
        annual_cost_per_sqft=est.get("annual", {}).get("per_sqft_year", 0.0),
        reserve_per_year=est.get("reserve", {}).get("annual_reserve", 0.0),
        condition_band=est.get("condition_band", "good"), notes=notes,
    )
    plans_db.append(rec)
    return rec


def plan_view(rec: MaintenancePlan) -> Dict[str, Any]:
    view = _m(rec)
    view["annual_cost_text"] = format_pkr(rec.annual_cost)
    view["tier_label"] = MAINTENANCE_TIERS.get(rec.tier, {}).get("label", rec.tier)
    return view


def work_order_view(rec: WorkOrder) -> Dict[str, Any]:
    view = _m(rec)
    view["estimated_cost_text"] = format_pkr(rec.estimated_cost)
    return view
