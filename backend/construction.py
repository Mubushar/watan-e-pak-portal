"""
Construction intelligence wing for the Real Estate Portal
=========================================================

A self-contained, framework-free knowledge + estimator engine for the
*construction* side of real estate.  It carries:

* **Techniques** — a catalogue of modern and conventional construction systems
  (RCC frame, load-bearing, steel, PEB, precast, tunnel form, ICF, AAC blocks,
  facades, roofing, green building …) with cost factors, build speed, material
  and labour intensity, soil/seismic suitability, pros/cons, warranty and code
  references.
* **Materials** — unit rates, wastage, lead times, local availability,
  alternatives and eco-ratings for the materials used on a Pakistani site.
* **Cost analysis & estimation** — parameterised build-up of a project cost by
  BOQ element, rate analysis per line item, a material take-off, a phase-based
  timeline, per-city and per-quality multipliers, escalation, and a comparison
  of competing construction techniques.
* **Impact on real estate** — how the chosen technique and quality tier move
  market value, rent, yield, maintenance cost and payback.
* **Guidelines** — building codes and byelaws, zoning/setback/FAR/height rules,
  seismic design, fire safety, accessibility, environmental clearance, approval
  / NOC workflow, QA checklists and HSE rules.

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

CONSTRUCTION_CONFIG: Dict[str, Any] = {
    "currency": "PKR",
    "currency_symbol": "Rs",
    "default_city": "Lahore",
    "default_building_type": "house",
    "default_quality_tier": "standard",
    "default_system": "rcc_frame",
    "escalation_cagr": 0.085,               # construction-cost inflation p.a.
    "preliminaries_pct": 4.0,               # site setup, hoarding, water/power
    "contingency_pct": 3.0,
    "consultancy_pct": 4.0,                 # design, supervision, approvals
    "overhead_profit_pct": 10.0,
    "floor_premium_pct": 1.5,               # extra cost per floor above the 2nd
    "floor_premium_from": 2,
    "city_multipliers": {
        "Lahore": 1.00, "Karachi": 1.06, "Islamabad": 1.08, "Rawalpindi": 1.02,
        "Faisalabad": 0.97, "Multan": 0.95, "Peshawar": 0.98, "Quetta": 0.96,
        "Gujranwala": 0.97, "Hyderabad": 0.95,
    },
    # Turnkey cost per sq-ft of covered area by finish quality (structure + finishes + MEP)
    "quality_base_rate_sqft": {
        "economy": 3300.0, "standard": 4600.0, "premium": 6500.0, "luxury": 9500.0,
    },
    "quality_labels": {
        "economy": "Economy", "standard": "Standard",
        "premium": "Premium", "luxury": "Luxury",
    },
}

# building type -> (cost factor, default storeys, days per 1000 sq-ft of build)
BUILDING_TYPES: Dict[str, Dict[str, Any]] = {
    "house":     {"label": "House (independent)", "factor": 1.00, "storeys": 2, "days_per_1000sqft": 90.0},
    "floor":     {"label": "Floor / apartment unit", "factor": 1.06, "storeys": 1, "days_per_1000sqft": 80.0},
    "apartment": {"label": "Apartment building", "factor": 1.10, "storeys": 8, "days_per_1000sqft": 70.0},
    "building":  {"label": "Multi-storey building", "factor": 1.12, "storeys": 10, "days_per_1000sqft": 68.0},
    "office":    {"label": "Office / commercial", "factor": 1.14, "storeys": 6, "days_per_1000sqft": 72.0},
    "shop":      {"label": "Shop / retail", "factor": 1.05, "storeys": 2, "days_per_1000sqft": 78.0},
    "space":     {"label": "Open commercial space", "factor": 1.02, "storeys": 1, "days_per_1000sqft": 74.0},
    "warehouse": {"label": "Warehouse", "factor": 0.82, "storeys": 1, "days_per_1000sqft": 45.0},
    "shed":      {"label": "Shed / industrial", "factor": 0.74, "storeys": 1, "days_per_1000sqft": 38.0},
}

# ---- Construction techniques / systems -------------------------------------

CONSTRUCTION_SYSTEMS: List[Dict[str, Any]] = [
    {
        "key": "rcc_frame", "name": "RCC frame (cast-in-situ)",
        "category": "structure", "cost_factor": 1.00, "speed_floors_per_month": 1.5,
        "description": "Reinforced-cement-concrete columns, beams and slabs cast on site — the default for Pakistani houses and mid-rise buildings.",
        "suitable_for": ["house", "floor", "apartment", "building", "office", "shop"],
        "min_floors": 1, "max_floors": 40,
        "material_intensity": "high", "labour_intensity": "high", "skill_level": "skilled",
        "equipment": ["mixer / batching", "vibrator", "scaffolding", "crane (high-rise)"],
        "soil_suitability": ["any"], "seismic_rating": "good",
        "pros": ["Well-understood and widely available", "Monolithic, rigid and durable",
                 "Easy to extend or modify later"],
        "cons": ["Slow — long curing periods", "Weather-sensitive on site",
                 "Material wastage and site quality risk"],
        "sustainability": "moderate", "warranty_years": 50,
        "code_refs": ["PEC BCP-SP", "Pakistan Building Code 2021"],
        "tags": ["conventional", "rc", "structure"],
    },
    {
        "key": "load_bearing", "name": "Load-bearing brick masonry",
        "category": "structure", "cost_factor": 0.92, "speed_floors_per_month": 1.1,
        "description": "Thick brick walls carry the floors — economical up to two or three storeys, common in older housing stock.",
        "suitable_for": ["house", "shed"],
        "min_floors": 1, "max_floors": 3,
        "material_intensity": "high", "labour_intensity": "high", "skill_level": "skilled",
        "equipment": ["scaffolding", "mixer"],
        "soil_suitability": ["sandy_loam", "clay", "silt"], "seismic_rating": "moderate",
        "pros": ["Low material cost", "Good thermal mass", "No formwork needed"],
        "cons": ["Limited height", "Weak in earthquakes", "Hard to reconfigure"],
        "sustainability": "low", "warranty_years": 40,
        "code_refs": ["Pakistan Building Code 2021"],
        "tags": ["conventional", "masonry"],
    },
    {
        "key": "confined_masonry", "name": "Confined masonry (reinforced)",
        "category": "structure", "cost_factor": 0.95, "speed_floors_per_month": 1.3,
        "description": "Load-bearing masonry with reinforced concrete tie columns and bands — a seismically safer upgrade to plain masonry.",
        "suitable_for": ["house", "floor"],
        "min_floors": 1, "max_floors": 4,
        "material_intensity": "high", "labour_intensity": "high", "skill_level": "skilled",
        "equipment": ["mixer", "scaffolding"],
        "soil_suitability": ["sandy_loam", "clay", "silt"], "seismic_rating": "good",
        "pros": ["Much better seismic behaviour than plain masonry", "Low cost",
                 "Familiar to local masons"],
        "cons": ["Still height-limited", "Careful detailing required"],
        "sustainability": "moderate", "warranty_years": 45,
        "code_refs": ["Pakistan Building Code 2021", "BCP-SP 2007"],
        "tags": ["masonry", "seismic"],
    },
    {
        "key": "steel_frame", "name": "Structural steel frame",
        "category": "structure", "cost_factor": 1.18, "speed_floors_per_month": 2.5,
        "description": "Hot-rolled steel sections with composite decks — fast, tall and long-span capable.",
        "suitable_for": ["building", "office", "apartment", "warehouse"],
        "min_floors": 2, "max_floors": 60,
        "material_intensity": "medium", "labour_intensity": "medium", "skill_level": "highly skilled",
        "equipment": ["mobile crane", "welding sets", "torque tools"],
        "soil_suitability": ["rock", "sandy_loam", "any"], "seismic_rating": "very good",
        "pros": ["Very fast erection", "Excellent seismic performance", "Long spans, fewer columns"],
        "cons": ["Higher material cost", "Fire-proofing required", "Specialist fabrication"],
        "sustainability": "moderate", "warranty_years": 50,
        "code_refs": ["AISC", "Pakistan Building Code 2021"],
        "tags": ["steel", "high-rise"],
    },
    {
        "key": "peb", "name": "Pre-engineered building (PEB)",
        "category": "structure", "cost_factor": 1.05, "speed_floors_per_month": 2.2,
        "description": "Factory-built tapered steel frames clad in metal — the standard for warehouses and industrial sheds.",
        "suitable_for": ["warehouse", "shed", "space"],
        "min_floors": 1, "max_floors": 2,
        "material_intensity": "medium", "labour_intensity": "low", "skill_level": "skilled",
        "equipment": ["mobile crane", "boom lift"],
        "soil_suitability": ["any"], "seismic_rating": "good",
        "pros": ["Very fast and clean", "Large clear spans", "Low maintenance cladding"],
        "cons": ["Industrial aesthetic", "Less suited to habitable use"],
        "sustainability": "moderate", "warranty_years": 25,
        "code_refs": ["MBMA", "Pakistan Building Code 2021"],
        "tags": ["steel", "industrial"],
    },
    {
        "key": "precast", "name": "Precast concrete system",
        "category": "structure", "cost_factor": 1.12, "speed_floors_per_month": 3.0,
        "description": "Factory-cast walls, columns, beams and hollow-core slabs assembled on site — consistent quality and speed.",
        "suitable_for": ["apartment", "building", "warehouse"],
        "min_floors": 4, "max_floors": 40,
        "material_intensity": "medium", "labour_intensity": "low", "skill_level": "highly skilled",
        "equipment": ["tower/modular crane", "transport fleet", "precast yard"],
        "soil_suitability": ["any"], "seismic_rating": "good",
        "pros": ["Fast, repeatable, high quality", "Less on-site labour and waste"],
        "cons": ["Needs a casting yard and cranes", "Heavy transport logistics", "Less flexible"],
        "sustainability": "good", "warranty_years": 50,
        "code_refs": ["PCI", "Pakistan Building Code 2021"],
        "tags": ["precast", "industrialised"],
    },
    {
        "key": "tunnel_form", "name": "Tunnel / aluminium formwork",
        "category": "structure", "cost_factor": 1.08, "speed_floors_per_month": 3.5,
        "description": "Monolithic tunnel or aluminium forms cast a wall-and-slab cell every cycle — the workhorse of large apartment schemes.",
        "suitable_for": ["apartment", "building", "office"],
        "min_floors": 5, "max_floors": 50,
        "material_intensity": "medium", "labour_intensity": "medium", "skill_level": "highly skilled",
        "equipment": ["tower crane", "formwork sets", "concrete pump"],
        "soil_suitability": ["any"], "seismic_rating": "very good",
        "pros": ["Fast slab cycles (3–7 days)", "Repeated identical units", "Excellent finish"],
        "cons": ["High formwork capital cost", "Repetitive layouts only", "Needs crane access"],
        "sustainability": "good", "warranty_years": 50,
        "code_refs": ["Pakistan Building Code 2021"],
        "tags": ["formwork", "high-rise", "speed"],
    },
    {
        "key": "icf", "name": "Insulated concrete formwork (ICF)",
        "category": "structure", "cost_factor": 1.12, "speed_floors_per_month": 1.6,
        "description": "Hollow EPS forms stacked and filled with concrete — insulated, airtight walls built in one operation.",
        "suitable_for": ["house", "floor", "apartment"],
        "min_floors": 1, "max_floors": 5,
        "material_intensity": "low", "labour_intensity": "medium", "skill_level": "skilled",
        "equipment": ["concrete pump", "scaffolding"],
        "soil_suitability": ["any"], "seismic_rating": "good",
        "pros": ["Excellent thermal insulation", "Fast wall build", "Low air leakage"],
        "cons": ["Specialist supply chain", "Concrete pump needed", "Less familiar locally"],
        "sustainability": "high", "warranty_years": 50,
        "code_refs": ["ACI", "Pakistan Building Code 2021"],
        "tags": ["insulation", "energy", "speed"],
    },
    {
        "key": "jump_form", "name": "Jump / slip form (core & shear wall)",
        "category": "structure", "cost_factor": 1.10, "speed_floors_per_month": 4.0,
        "description": "Self-climbing formwork for lift cores and shear walls — the fastest vertical system on tall towers.",
        "suitable_for": ["building", "apartment", "office"],
        "min_floors": 10, "max_floors": 80,
        "material_intensity": "medium", "labour_intensity": "medium", "skill_level": "expert",
        "equipment": ["self-climbing form", "tower crane", "concrete pump"],
        "soil_suitability": ["any", "rock"], "seismic_rating": "very good",
        "pros": ["Very fast vertical build", "Excellent surface finish", "Safe working platforms"],
        "cons": ["High setup cost", "Only viable on tall towers"],
        "sustainability": "good", "warranty_years": 50,
        "code_refs": ["Pakistan Building Code 2021"],
        "tags": ["formwork", "tall-building"],
    },
    {
        "key": "aac_blocks", "name": "AAC block masonry",
        "category": "envelope", "cost_factor": 1.03, "speed_floors_per_month": 2.0,
        "description": "Autoclaved aerated concrete blocks replace bricks — lighter, faster and better insulating.",
        "suitable_for": ["house", "floor", "apartment", "building", "office"],
        "min_floors": 1, "max_floors": 50,
        "material_intensity": "medium", "labour_intensity": "medium", "skill_level": "semi-skilled",
        "equipment": ["block trolley", "mortar mixer"],
        "soil_suitability": ["any"], "seismic_rating": "n/a",
        "pros": ["Lighter dead load", "Faster to lay", "Better thermal and fire performance"],
        "cons": ["Requires thin-bed mortar", "Careful handling (brittle)"],
        "sustainability": "high", "warranty_years": 30,
        "code_refs": ["PSQCA", "Pakistan Building Code 2021"],
        "tags": ["masonry", "lightweight"],
    },
    {
        "key": "fly_ash_bricks", "name": "Fly-ash / FPS brick masonry",
        "category": "envelope", "cost_factor": 0.99, "speed_floors_per_month": 1.8,
        "description": "Fly-ash and sand-lime bricks — dimensionally consistent and more sustainable than clay bricks.",
        "suitable_for": ["house", "floor", "apartment", "building", "shop"],
        "min_floors": 1, "max_floors": 40,
        "material_intensity": "high", "labour_intensity": "high", "skill_level": "semi-skilled",
        "equipment": ["scaffolding", "mixer"],
        "soil_suitability": ["any"], "seismic_rating": "n/a",
        "pros": ["Uniform size, less mortar", "Reuses industrial ash", "Good strength"],
        "cons": ["Availability varies by region"],
        "sustainability": "high", "warranty_years": 30,
        "code_refs": ["PSQCA"],
        "tags": ["masonry", "sustainable"],
    },
    {
        "key": "stone_facade", "name": "Natural stone cladding facade",
        "category": "facade", "cost_factor": 1.15, "speed_floors_per_month": 2.0,
        "description": "Sandstone/granite cladding over a backing wall — a premium, durable external finish.",
        "suitable_for": ["house", "building", "office", "shop"],
        "min_floors": 1, "max_floors": 40,
        "material_intensity": "high", "labour_intensity": "high", "skill_level": "skilled",
        "equipment": ["scaffolding", "cutters", "hoist"],
        "soil_suitability": ["any"], "seismic_rating": "n/a",
        "pros": ["Prestige appearance", "Very durable", "Low maintenance"],
        "cons": ["Heavy", "Costly and slow"],
        "sustainability": "moderate", "warranty_years": 25,
        "code_refs": ["PSQCA"],
        "tags": ["facade", "premium"],
    },
    {
        "key": "acp_facade", "name": "ACP / aluminium-glass curtain wall",
        "category": "facade", "cost_factor": 1.20, "speed_floors_per_month": 2.6,
        "description": "Aluminium composite panels and structural glazing — a modern commercial curtain wall.",
        "suitable_for": ["office", "building", "shop", "apartment"],
        "min_floors": 2, "max_floors": 60,
        "material_intensity": "medium", "labour_intensity": "medium", "skill_level": "highly skilled",
        "equipment": ["cradles", "hoist", "cutting shop"],
        "soil_suitability": ["any"], "seismic_rating": "n/a",
        "pros": ["Contemporary look", "Fast, light envelope", "Good daylighting"],
        "cons": ["Thermal bridging risk", "Specialist installer", "Cleaning needed"],
        "sustainability": "moderate", "warranty_years": 15,
        "code_refs": ["ASTM", "Pakistan Building Code 2021"],
        "tags": ["facade", "commercial", "glazing"],
    },
    {
        "key": "gi_truss_roof", "name": "GI / steel truss roof",
        "category": "roofing", "cost_factor": 0.98, "speed_floors_per_month": 2.4,
        "description": "Light steel trusses with GI/metal sheeting — light, fast and economical for large spans.",
        "suitable_for": ["warehouse", "shed", "house", "space"],
        "min_floors": 1, "max_floors": 3,
        "material_intensity": "medium", "labour_intensity": "medium", "skill_level": "skilled",
        "equipment": ["welding sets", "crane", "roof access"],
        "soil_suitability": ["any"], "seismic_rating": "good",
        "pros": ["Light dead load", "Fast erection", "Wide spans, no columns"],
        "cons": ["Noise in rain", "Needs insulation for comfort", "Corrosion risk"],
        "sustainability": "moderate", "warranty_years": 20,
        "code_refs": ["Pakistan Building Code 2021"],
        "tags": ["roofing", "steel"],
    },
    {
        "key": "flat_rcc_roof", "name": "Flat RCC roof with waterproofing",
        "category": "roofing", "cost_factor": 1.00, "speed_floors_per_month": 1.5,
        "description": "Cast RCC slab finished with screed and membrane/cementitious waterproofing — the standard usable roof.",
        "suitable_for": ["house", "floor", "apartment", "building", "office", "shop"],
        "min_floors": 1, "max_floors": 40,
        "material_intensity": "high", "labour_intensity": "high", "skill_level": "skilled",
        "equipment": ["mixer", "vibrator"],
        "soil_suitability": ["any"], "seismic_rating": "good",
        "pros": ["Usable terrace", "Durable if waterproofed well"],
        "cons": ["Thermal gain", "Waterproofing must be maintained"],
        "sustainability": "moderate", "warranty_years": 10,
        "code_refs": ["Pakistan Building Code 2021"],
        "tags": ["roofing", "rc"],
    },
    {
        "key": "drywall_partition", "name": "Drywall / gypsum partitions",
        "category": "partition", "cost_factor": 1.02, "speed_floors_per_month": 3.0,
        "description": "Lightweight stud-and-board partitions for fast, serviceable interior layouts.",
        "suitable_for": ["office", "apartment", "building", "shop", "floor"],
        "min_floors": 1, "max_floors": 60,
        "material_intensity": "low", "labour_intensity": "low", "skill_level": "semi-skilled",
        "equipment": ["hand tools", "lift"],
        "soil_suitability": ["any"], "seismic_rating": "n/a",
        "pros": ["Very fast and clean", "Easy to route services", "Reconfigurable"],
        "cons": ["Less robust", "Acoustic detailing needed"],
        "sustainability": "good", "warranty_years": 10,
        "code_refs": ["ASTM"],
        "tags": ["interior", "partition", "fast"],
    },
    {
        "key": "green_building", "name": "Green / energy-efficient construction",
        "category": "green", "cost_factor": 1.06, "speed_floors_per_month": 1.8,
        "description": "Insulated envelope, shading, solar, rainwater harvesting and efficient MEP designed together.",
        "suitable_for": ["house", "floor", "apartment", "building", "office"],
        "min_floors": 1, "max_floors": 50,
        "material_intensity": "medium", "labour_intensity": "medium", "skill_level": "highly skilled",
        "equipment": ["insulation tools", "solar rig", "testing kit"],
        "soil_suitability": ["any"], "seismic_rating": "n/a",
        "pros": ["Much lower running cost", "Better comfort", "Higher resale appeal"],
        "cons": ["Higher upfront cost", "Requires integrated design"],
        "sustainability": "very high", "warranty_years": 25,
        "code_refs": ["Pakistan Green Building Council", "IGBC"],
        "tags": ["green", "energy", "sustainability"],
    },
]


def construction_systems(category: Optional[str] = None) -> List[Dict[str, Any]]:
    rows = list(CONSTRUCTION_SYSTEMS)
    if category:
        rows = [s for s in rows if s["category"] == category]
    return rows


def find_system(key: Optional[str]) -> Optional[Dict[str, Any]]:
    if not key:
        return None
    k = str(key).strip().lower()
    return next((s for s in CONSTRUCTION_SYSTEMS if s["key"] == k), None)


# ---- Materials -------------------------------------------------------------

MATERIALS: List[Dict[str, Any]] = [
    {"key": "cement_opc", "name": "Cement — OPC", "category": "binding", "unit": "bag (50 kg)",
     "unit_rate": 1285.0, "wastage_pct": 3.0, "lead_time_days": 2, "availability": "nationwide",
     "alternatives": ["SRC cement", "blended cement"], "eco_rating": "moderate"},
    {"key": "cement_src", "name": "Cement — sulphate-resisting", "category": "binding", "unit": "bag (50 kg)",
     "unit_rate": 1475.0, "wastage_pct": 3.0, "lead_time_days": 4, "availability": "regional",
     "alternatives": [], "eco_rating": "moderate"},
    {"key": "cement_white", "name": "White cement", "category": "binding", "unit": "bag (50 kg)",
     "unit_rate": 2450.0, "wastage_pct": 4.0, "lead_time_days": 6, "availability": "regional",
     "alternatives": [], "eco_rating": "moderate"},
    {"key": "steel_60", "name": "Reinforcement steel — Grade 60", "category": "steel", "unit": "kg",
     "unit_rate": 262.0, "wastage_pct": 4.0, "lead_time_days": 5, "availability": "nationwide",
     "alternatives": ["Grade 40"], "eco_rating": "high (recyclable)"},
    {"key": "steel_40", "name": "Reinforcement steel — Grade 40", "category": "steel", "unit": "kg",
     "unit_rate": 252.0, "wastage_pct": 4.0, "lead_time_days": 5, "availability": "nationwide",
     "alternatives": ["Grade 60"], "eco_rating": "high (recyclable)"},
    {"key": "structural_steel", "name": "Structural steel sections", "category": "steel", "unit": "kg",
     "unit_rate": 315.0, "wastage_pct": 3.0, "lead_time_days": 12, "availability": "regional",
     "alternatives": [], "eco_rating": "high (recyclable)"},
    {"key": "sand", "name": "Sand (fine aggregate)", "category": "aggregate", "unit": "cft",
     "unit_rate": 78.0, "wastage_pct": 8.0, "lead_time_days": 2, "availability": "nationwide",
     "alternatives": ["crushed sand"], "eco_rating": "moderate"},
    {"key": "aggregate", "name": "Crushed aggregate (bajri)", "category": "aggregate", "unit": "cft",
     "unit_rate": 92.0, "wastage_pct": 6.0, "lead_time_days": 2, "availability": "nationwide",
     "alternatives": ["recycled aggregate"], "eco_rating": "moderate"},
    {"key": "brick_a", "name": "Bricks — A class", "category": "masonry", "unit": "no",
     "unit_rate": 24.0, "wastage_pct": 5.0, "lead_time_days": 4, "availability": "nationwide",
     "alternatives": ["fly-ash brick", "AAC block"], "eco_rating": "low"},
    {"key": "fly_ash_brick", "name": "Fly-ash / FPS brick", "category": "masonry", "unit": "no",
     "unit_rate": 28.0, "wastage_pct": 3.0, "lead_time_days": 6, "availability": "regional",
     "alternatives": ["A class brick"], "eco_rating": "high"},
    {"key": "aac_block", "name": "AAC block", "category": "masonry", "unit": "cft",
     "unit_rate": 165.0, "wastage_pct": 4.0, "lead_time_days": 8, "availability": "regional",
     "alternatives": ["brick", "fly-ash brick"], "eco_rating": "high"},
    {"key": "floor_tile", "name": "Floor tiles (porcelain)", "category": "finish", "unit": "sqft",
     "unit_rate": 285.0, "wastage_pct": 8.0, "lead_time_days": 7, "availability": "nationwide",
     "alternatives": ["marble", "vinyl"], "eco_rating": "moderate"},
    {"key": "marble", "name": "Marble (local)", "category": "finish", "unit": "sqft",
     "unit_rate": 420.0, "wastage_pct": 12.0, "lead_time_days": 10, "availability": "nationwide",
     "alternatives": ["tiles", "granite"], "eco_rating": "moderate"},
    {"key": "paint_emulsion", "name": "Emulsion paint (interior)", "category": "finish", "unit": "litre",
     "unit_rate": 620.0, "wastage_pct": 5.0, "lead_time_days": 4, "availability": "nationwide",
     "alternatives": ["weather coat", "distemper"], "eco_rating": "low"},
    {"key": "paint_weather", "name": "Weather-coat paint (exterior)", "category": "finish", "unit": "litre",
     "unit_rate": 1150.0, "wastage_pct": 6.0, "lead_time_days": 4, "availability": "nationwide",
     "alternatives": ["texture coat"], "eco_rating": "low"},
    {"key": "waterproof_membrane", "name": "Waterproofing membrane", "category": "waterproofing", "unit": "sqft",
     "unit_rate": 145.0, "wastage_pct": 10.0, "lead_time_days": 8, "availability": "regional",
     "alternatives": ["cementitious coating", "bitumen"], "eco_rating": "moderate"},
    {"key": "pvc_pipe", "name": "PVC drainage pipe", "category": "plumbing", "unit": "rft",
     "unit_rate": 320.0, "wastage_pct": 6.0, "lead_time_days": 5, "availability": "nationwide",
     "alternatives": ["uPVC"], "eco_rating": "moderate"},
    {"key": "gi_pipe", "name": "GI water pipe", "category": "plumbing", "unit": "rft",
     "unit_rate": 415.0, "wastage_pct": 6.0, "lead_time_days": 5, "availability": "nationwide",
     "alternatives": ["PPRC", "CPVC"], "eco_rating": "moderate"},
    {"key": "electrical_wire", "name": "Copper electric wire", "category": "electrical", "unit": "m",
     "unit_rate": 185.0, "wastage_pct": 5.0, "lead_time_days": 5, "availability": "nationwide",
     "alternatives": ["aluminium (derated)"], "eco_rating": "moderate"},
    {"key": "floor_area_conduit", "name": "PVC conduit & boxes", "category": "electrical", "unit": "rft",
     "unit_rate": 95.0, "wastage_pct": 7.0, "lead_time_days": 5, "availability": "nationwide",
     "alternatives": [], "eco_rating": "moderate"},
    {"key": "flush_door", "name": "Flush door (with frame)", "category": "joinery", "unit": "no",
     "unit_rate": 32000.0, "wastage_pct": 2.0, "lead_time_days": 12, "availability": "nationwide",
     "alternatives": ["solid wood door"], "eco_rating": "moderate"},
    {"key": "aluminium_window", "name": "Aluminium window (per sqft)", "category": "joinery", "unit": "sqft",
     "unit_rate": 1450.0, "wastage_pct": 5.0, "lead_time_days": 15, "availability": "regional",
     "alternatives": ["uPVC window", "wood"], "eco_rating": "moderate"},
    {"key": "upvc_window", "name": "uPVC window (per sqft)", "category": "joinery", "unit": "sqft",
     "unit_rate": 1650.0, "wastage_pct": 5.0, "lead_time_days": 18, "availability": "regional",
     "alternatives": ["aluminium"], "eco_rating": "high"},
    {"key": "insulation_board", "name": "EPS / XPS insulation board", "category": "insulation", "unit": "sqft",
     "unit_rate": 120.0, "wastage_pct": 8.0, "lead_time_days": 10, "availability": "regional",
     "alternatives": ["mineral wool"], "eco_rating": "moderate"},
]


def materials(category: Optional[str] = None) -> List[Dict[str, Any]]:
    rows = list(MATERIALS)
    if category:
        rows = [m for m in rows if m["category"] == category]
    return rows


def find_material(key: Optional[str]) -> Optional[Dict[str, Any]]:
    if not key:
        return None
    k = str(key).strip().lower()
    return next((m for m in MATERIALS if m["key"] == k), None)


# ---- Rate analysis / BOQ element unit rates ---------------------------------

# Each line: element -> {unit, material, labour, plant, overhead} in PKR per unit.
ELEMENT_RATES: Dict[str, Dict[str, Any]] = {
    "excavation":        {"label": "Earthwork & excavation", "unit": "cft", "material": 0, "labour": 28, "plant": 22, "overhead": 5},
    "pcc":               {"label": "Plain cement concrete (1:4:8)", "unit": "cft", "material": 210, "labour": 55, "plant": 20, "overhead": 28},
    "rcc":               {"label": "Reinforced concrete (1:2:4)", "unit": "cft", "material": 560, "labour": 95, "plant": 45, "overhead": 70},
    "reinforcement":     {"label": "Steel reinforcement fixing", "unit": "kg", "material": 262, "labour": 18, "plant": 3, "overhead": 14},
    "brickwork":         {"label": "Brick masonry (9\")", "unit": "cft", "material": 340, "labour": 75, "plant": 6, "overhead": 38},
    "blockwork":         {"label": "AAC block masonry", "unit": "cft", "material": 300, "labour": 55, "plant": 5, "overhead": 32},
    "plaster":           {"label": "Cement plaster (1:4)", "unit": "sqft", "material": 48, "labour": 32, "plant": 2, "overhead": 8},
    "flooring":          {"label": "Floor tiling & skirting", "unit": "sqft", "material": 285, "labour": 95, "plant": 4, "overhead": 40},
    "painting":          {"label": "Painting (2 coats)", "unit": "sqft", "material": 42, "labour": 26, "plant": 2, "overhead": 8},
    "waterproofing":     {"label": "Roof waterproofing membrane", "unit": "sqft", "material": 145, "labour": 55, "plant": 6, "overhead": 22},
    "doors_windows":     {"label": "Doors, windows & joinery", "unit": "lump", "material": 0, "labour": 0, "plant": 0, "overhead": 0},
    "plumbing":          {"label": "Plumbing & sanitary", "unit": "lump", "material": 0, "labour": 0, "plant": 0, "overhead": 0},
    "electrical":        {"label": "Electrical & lighting", "unit": "lump", "material": 0, "labour": 0, "plant": 0, "overhead": 0},
    "hvac":              {"label": "HVAC & ventilation", "unit": "lump", "material": 0, "labour": 0, "plant": 0, "overhead": 0},
    "fire_fighting":     {"label": "Fire-fighting & safety", "unit": "lump", "material": 0, "labour": 0, "plant": 0, "overhead": 0},
    "lifts":             {"label": "Elevators / vertical transport", "unit": "lump", "material": 0, "labour": 0, "plant": 0, "overhead": 0},
}


def rate_analysis(element: str, city: Optional[str] = None) -> Dict[str, Any]:
    """Material / labour / plant / overhead build-up of one BOQ element rate."""
    row = ELEMENT_RATES.get(str(element).strip().lower())
    if not row:
        return {"error": f"Unknown element: {element}", "elements": sorted(ELEMENT_RATES)}
    city_factor = CONSTRUCTION_CONFIG["city_multipliers"].get(
        city or CONSTRUCTION_CONFIG["default_city"], 1.0)
    labour = round(row["labour"] * city_factor, 2)
    plant = round(row["plant"] * city_factor, 2)
    overhead = round(row["overhead"] * city_factor, 2)
    material = float(row["material"])
    total = round(material + labour + plant + overhead, 2)
    return {
        "element": element, "label": row["label"], "unit": row["unit"],
        "city": city or CONSTRUCTION_CONFIG["default_city"], "city_factor": city_factor,
        "breakdown": {"material": material, "labour": labour, "plant": plant, "overhead": overhead},
        "total_rate": total,
        "shares": {
            "material": round(material / total * 100, 1) if total else 0.0,
            "labour": round(labour / total * 100, 1) if total else 0.0,
            "plant": round(plant / total * 100, 1) if total else 0.0,
            "overhead": round(overhead / total * 100, 1) if total else 0.0,
        },
    }


# ---- Element cost shares ----------------------------------------------------

ELEMENT_BASE: Dict[str, float] = {
    "substructure": 9.0, "frame": 24.0, "masonry": 9.0, "roofing": 6.0,
    "plaster_paint": 9.0, "flooring": 8.0, "doors_windows": 7.0,
    "plumbing": 7.0, "electrical": 7.0, "hvac": 4.0, "external": 5.0,
    "fire": 2.0, "lifts": 3.0,
}
ELEMENT_LABELS: Dict[str, str] = {
    "substructure": "Substructure & foundation", "frame": "Frame — columns, beams & slabs",
    "masonry": "Masonry & blockwork", "roofing": "Roofing & waterproofing",
    "plaster_paint": "Plaster, putty & painting", "flooring": "Flooring & tiling",
    "doors_windows": "Doors, windows & joinery", "plumbing": "Sanitary, plumbing & water",
    "electrical": "Electrical & lighting", "hvac": "HVAC & ventilation",
    "external": "External works & landscaping", "fire": "Fire-fighting & safety",
    "lifts": "Vertical transport (lifts)",
}
ELEMENT_CATEGORY: Dict[str, str] = {
    "substructure": "structure", "frame": "structure", "masonry": "structure",
    "roofing": "envelope", "plaster_paint": "finishes", "flooring": "finishes",
    "doors_windows": "finishes", "plumbing": "mep", "electrical": "mep",
    "hvac": "mep", "external": "external", "fire": "mep", "lifts": "mep",
}
# element multipliers per building type (0 = not applicable)
BUILDING_TYPE_ELEMENTS: Dict[str, Dict[str, float]] = {
    "house":     {"hvac": 0.0, "lifts": 0.0, "fire": 0.5},
    "floor":     {"lifts": 0.0, "hvac": 0.5, "fire": 0.5},
    "shop":      {"lifts": 0.0, "hvac": 0.5, "external": 1.0},
    "space":     {"lifts": 0.0, "hvac": 0.5, "fire": 0.5},
    "warehouse": {"lifts": 0.0, "hvac": 0.0, "fire": 1.5, "plaster_paint": 0.4,
                  "flooring": 0.3, "doors_windows": 0.4, "frame": 0.8, "external": 0.6},
    "shed":      {"lifts": 0.0, "hvac": 0.0, "fire": 0.5, "plaster_paint": 0.2,
                  "flooring": 0.2, "doors_windows": 0.3, "frame": 0.7, "masonry": 0.6},
    "apartment": {"lifts": 1.6, "hvac": 0.6, "fire": 1.2},
    "building":  {"lifts": 1.8, "hvac": 1.0, "fire": 1.4},
    "office":    {"lifts": 1.6, "hvac": 1.5, "fire": 1.3, "plaster_paint": 0.9, "flooring": 0.9},
}
TIER_CATEGORY_MULT: Dict[str, Dict[str, float]] = {
    "economy": {"structure": 1.05, "envelope": 0.95, "finishes": 0.80, "mep": 0.85, "external": 0.85},
    "standard": {"structure": 1.00, "envelope": 1.00, "finishes": 1.00, "mep": 1.00, "external": 1.00},
    "premium": {"structure": 1.00, "envelope": 1.10, "finishes": 1.25, "mep": 1.15, "external": 1.10},
    "luxury":  {"structure": 1.00, "envelope": 1.20, "finishes": 1.55, "mep": 1.35, "external": 1.25},
}


def element_shares(building_type: str, quality_tier: str) -> Dict[str, float]:
    """Relative cost share (%) of each BOQ element, normalised to 100."""
    bt = building_type if building_type in BUILDING_TYPES else "house"
    tier = quality_tier if quality_tier in TIER_CATEGORY_MULT else "standard"
    overrides = BUILDING_TYPE_ELEMENTS.get(bt, {})
    cat_mult = TIER_CATEGORY_MULT[tier]
    raw: Dict[str, float] = {}
    for el, base in ELEMENT_BASE.items():
        mult = overrides.get(el, 1.0)
        if mult <= 0:
            continue
        raw[el] = base * mult * cat_mult.get(ELEMENT_CATEGORY[el], 1.0)
    total = sum(raw.values()) or 1.0
    return {el: round(v / total * 100, 3) for el, v in raw.items()}


# ---- Phases, timeline, trades ----------------------------------------------

CONSTRUCTION_PHASES: List[Dict[str, Any]] = [
    {"key": "mobilisation", "name": "Mobilisation & site setup", "weight": 3.0, "depends_on": []},
    {"key": "excavation", "name": "Excavation & earthwork", "weight": 5.0, "depends_on": ["mobilisation"]},
    {"key": "foundation", "name": "Foundation & substructure", "weight": 12.0, "depends_on": ["excavation"]},
    {"key": "structure", "name": "Superstructure (frame & slabs)", "weight": 30.0, "depends_on": ["foundation"]},
    {"key": "masonry", "name": "Masonry & walling", "weight": 10.0, "depends_on": ["structure"]},
    {"key": "mep_rough", "name": "MEP first fix (concealed)", "weight": 8.0, "depends_on": ["masonry"]},
    {"key": "plaster", "name": "Plaster, screed & waterproofing", "weight": 9.0, "depends_on": ["mep_rough"]},
    {"key": "finishes", "name": "Flooring, joinery & painting", "weight": 12.0, "depends_on": ["plaster"]},
    {"key": "mep_final", "name": "MEP second fix & fittings", "weight": 7.0, "depends_on": ["finishes"]},
    {"key": "external", "name": "External works & landscaping", "weight": 3.0, "depends_on": ["finishes"]},
    {"key": "handover", "name": "Testing, snagging & handover", "weight": 1.0, "depends_on": ["mep_final", "external"]},
]

TRADES: List[Dict[str, Any]] = [
    {"key": "mason", "name": "Mason / brick layer", "daily_wage": 3500},
    {"key": "carpenter", "name": "Carpenter (shuttering)", "daily_wage": 3800},
    {"key": "steel_fixer", "name": "Steel fixer / bar bender", "daily_wage": 3900},
    {"key": "plumber", "name": "Plumber", "daily_wage": 4200},
    {"key": "electrician", "name": "Electrician", "daily_wage": 4500},
    {"key": "painter", "name": "Painter", "daily_wage": 3200},
    {"key": "tile_layer", "name": "Tile / marble layer", "daily_wage": 4000},
    {"key": "welder", "name": "Welder / fabricator", "daily_wage": 4600},
    {"key": "labourer", "name": "Unskilled labourer", "daily_wage": 1600},
    {"key": "foreman", "name": "Foreman / supervisor", "daily_wage": 6500},
    {"key": "surveyor", "name": "Surveyor", "daily_wage": 7000},
    {"key": "operator", "name": "Plant operator", "daily_wage": 5200},
]


def trades() -> List[Dict[str, Any]]:
    return list(TRADES)


# ---- Soil, seismic, guidelines, approvals, QA, HSE --------------------------

SOIL_TYPES: Dict[str, Dict[str, Any]] = {
    "rock":        {"label": "Rock / gravel", "bearing_capacity_kpa": 450, "foundation": "Pad / strip footings directly on rock"},
    "sandy_loam":  {"label": "Sandy loam", "bearing_capacity_kpa": 150, "foundation": "Pad or strip footings below 5 ft"},
    "sandy":       {"label": "Loose sand", "bearing_capacity_kpa": 100, "foundation": "Raft or widened pad footings"},
    "clay":        {"label": "Stiff clay", "bearing_capacity_kpa": 90, "foundation": "Raft foundation preferred; watch swelling"},
    "silt":        {"label": "Silt / soft", "bearing_capacity_kpa": 60, "foundation": "Raft or piles; dewatering may be needed"},
    "reclaimed":   {"label": "Filled / reclaimed", "bearing_capacity_kpa": 45, "foundation": "Piles or ground improvement + raft"},
}

SEISMIC_ZONES: Dict[str, Dict[str, Any]] = {
    "1":  {"label": "Zone 1 (low)", "factor": 0.05, "regions": ["Central Punjab plains"], "requirement": "Basic detailing"},
    "2A": {"label": "Zone 2A (moderate)", "factor": 0.10, "regions": ["Lahore", "Faisalabad", "Islamabad (parts)"], "requirement": "Confined masonry or RC frame with ties"},
    "2B": {"label": "Zone 2B (moderate–high)", "factor": 0.15, "regions": ["Islamabad", "Rawalpindi", "Peshawar"], "requirement": "Ductile RC/steel detailing, shear walls"},
    "3":  {"label": "Zone 3 (high)", "factor": 0.24, "regions": ["Karachi", "Quetta (parts)"], "requirement": "Ductile frames, shear walls, foundations to code"},
    "4":  {"label": "Zone 4 (very high)", "factor": 0.36, "regions": ["Northern areas", "Quetta"], "requirement": "Special moment frames, base isolation considered"},
}

CONSTRUCTION_GUIDELINES: List[Dict[str, Any]] = [
    {"key": "zoning_setbacks", "title": "Zoning, setbacks & coverage", "category": "zoning",
     "authority": "LDA / CDA / KDA / SBCA", "code": "Local building byelaws",
     "summary": "Every plot must leave front/side/rear setbacks and respect the maximum ground coverage of its society.",
     "rules": ["Front setback typically 5–10 ft, rear 5 ft, sides 0–5 ft (plot-size dependent)",
               "Ground coverage usually capped at 70–90% of the plot",
               "Boundary walls and gates must match society elevations"],
     "applies_to": ["house", "floor", "apartment", "building", "shop"], "penalty": "Stop-work notice / sealing"},
    {"key": "far_height", "title": "Far / FSI & height limits", "category": "zoning",
     "authority": "LDA / CDA / KDA", "code": "Building byelaws / master plan",
     "summary": "Floor-area ratio and height caps are set by the authority and vary by road width and zone.",
     "rules": ["FAR is granted with building-plan approval and cannot be sold or exceeded",
               "Height limits depend on road width; corner plots get relief",
               "Basements count toward FAR where habitable"],
     "applies_to": ["apartment", "building", "office", "shop"], "penalty": "Demolition order"},
    {"key": "structural_design", "title": "Structural design & supervision", "category": "structural",
     "authority": "Pakistan Engineering Council (PEC)", "code": "PEC Byelaws; Pakistan Building Code 2021",
     "summary": "Designs must be prepared and supervised by PEC-registered engineers.",
     "rules": ["Structural drawings signed by a registered engineer",
               "Concrete mix design and cube testing to PSQCA standards",
               "Change of structure requires revised approval"],
     "applies_to": ["house", "floor", "apartment", "building", "office", "warehouse"],
     "penalty": "Invalid approval; liability in failure"},
    {"key": "seismic_design", "title": "Seismic design requirements", "category": "seismic",
     "authority": "PEC / BCP", "code": "BCP-SP 2007 (seismic provisions)",
     "summary": "Buildings must be designed for the seismic zone of their site.",
     "rules": ["Identify the zone factor before design",
               "Provide ductile detailing, ties and shear walls as required",
               "Confined masonry for low-rise in zones 2A–2B"],
     "applies_to": ["house", "floor", "apartment", "building", "office"], "penalty": "Code violation"},
    {"key": "fire_safety", "title": "Fire safety & means of escape", "category": "fire",
     "authority": "Rescue 1122 / Civil Defence", "code": "Pakistan Fire Safety Code",
     "summary": "High-rise and commercial buildings need fire escape, detection and suppression.",
     "rules": ["At least two escape stairs for buildings over a threshold height",
               "Fire-rated doors, alarms, hose reels and extinguishers",
               "No combustible storage in escape routes"],
     "applies_to": ["apartment", "building", "office", "shop", "warehouse"], "penalty": "Occupancy refused"},
    {"key": "accessibility", "title": "Accessibility & disabled access", "category": "accessibility",
     "authority": "Local authority", "code": "Building byelaws / accessibility standards",
     "summary": "Public buildings must provide accessible routes, ramps and toilets.",
     "rules": ["Ramp gradients at entries for public buildings",
               "Accessible sanitary provision", "Lift dimensions to carry a wheelchair"],
     "applies_to": ["office", "shop", "building", "apartment"], "penalty": "Approval conditions"},
    {"key": "environmental", "title": "Environmental clearance & EIA", "category": "environmental",
     "authority": "EPA (provincial)", "code": "PEPA 1997 / EIA regulations",
     "summary": "Large projects need environmental screening or a full EIA before approval.",
     "rules": ["EIA/IEE as applicable to project size",
               "Stormwater, sewage and solid-waste management plan",
               "Dust, noise and traffic management during construction"],
     "applies_to": ["apartment", "building", "office", "warehouse"], "penalty": "Project halted"},
    {"key": "material_standards", "title": "Material standards & testing", "category": "quality",
     "authority": "PSQCA", "code": "Pakistan Standards",
     "summary": "Cement, steel, bricks and pipes must meet PSQCA standards with test certificates.",
     "rules": ["Cement to PS-232; steel to PS-1879 / ASTM", "Cube tests at 7 and 28 days",
               "Third-party testing for structural steel"],
     "applies_to": ["house", "floor", "apartment", "building", "office", "warehouse", "shed"],
     "penalty": "Rebuild / rejection"},
    {"key": "hse", "title": "Health, safety & environment on site", "category": "safety",
     "authority": "PEC / PESSI", "code": "Construction safety rules",
     "summary": "Sites must protect workers and the public throughout construction.",
     "rules": ["PPE: helmets, harnesses, boots, gloves",
               "Edge protection and safe scaffolding", "Worker welfare and first-aid provision"],
     "applies_to": ["house", "floor", "apartment", "building", "office", "warehouse", "shed"],
     "penalty": "Stop-work / fine"},
    {"key": "waterproofing_best", "title": "Waterproofing best practice", "category": "quality",
     "authority": "Trade best practice", "code": "Manufacturer systems",
     "summary": "Roofs, wet areas and basements must be waterproofed and tested before finishes.",
     "rules": ["Ponding test for roofs before screed", "Wet-area membrane turned up walls",
               "Positive and negative-side basement waterproofing"],
     "applies_to": ["house", "floor", "apartment", "building"], "penalty": "Seepage / warranty claims"},
    {"key": "energy", "title": "Energy efficiency & shading", "category": "green",
     "authority": "NEECA", "code": "Energy-conservation measures",
     "summary": "Orientation, shading, insulation and efficient services reduce running cost.",
     "rules": ["Insulate roof and west wall", "Shade west/south glazing",
               "Solar water heating and net metering where viable"],
     "applies_to": ["house", "floor", "apartment", "building", "office"], "penalty": "Higher running cost"},
    {"key": "approval_noc", "title": "Approvals & NOC workflow", "category": "approval",
     "authority": "Society / LDA / CDA / KDA / utilities", "code": "Approval procedures",
     "summary": "Construction cannot start before the society NOC, plan approval and utility NOCs.",
     "rules": ["Obtain society NOC and paid dues certificate",
               "Submit architectural + structural plans for approval",
               "Utility (power/water/sui-gas) NOCs before connection"],
     "applies_to": ["house", "floor", "apartment", "building", "office", "shop"],
     "penalty": "Demolition / disconnection"},
]


def guidelines(category: Optional[str] = None, authority: Optional[str] = None,
               building_type: Optional[str] = None) -> List[Dict[str, Any]]:
    rows = list(CONSTRUCTION_GUIDELINES)
    if category:
        rows = [g for g in rows if g["category"] == category]
    if authority:
        a = authority.lower()
        rows = [g for g in rows if a in g["authority"].lower()]
    if building_type:
        rows = [g for g in rows if building_type in g["applies_to"]]
    return rows


APPROVAL_STEPS: List[Dict[str, Any]] = [
    {"step": 1, "name": "Society NOC & dues clearance", "authority": "Housing society",
     "documents": ["Ownership/title documents", "Paid-dues certificate", "Undertaking"],
     "duration_days": 14, "fee_note": "Society service charges"},
    {"step": 2, "name": "Architectural plan approval", "authority": "LDA / CDA / KDA / SBCA",
     "documents": ["Site plan", "Floor plans", "Elevations", "Coverage statement"],
     "duration_days": 30, "fee_note": "Scrutiny + plan fee by covered area"},
    {"step": 3, "name": "Structural design approval", "authority": "Development authority (PEC engineer)",
     "documents": ["Structural drawings", "Design calculations", "Soil report"],
     "duration_days": 21, "fee_note": "Includes consultant charge"},
    {"step": 4, "name": "Utility NOCs", "authority": "Power / water / SNGPL",
     "documents": ["Approved plans", "Load request", "Deposit receipts"],
     "duration_days": 30, "fee_note": "Connection deposits"},
    {"step": 5, "name": "Environmental screening / EIA", "authority": "Provincial EPA",
     "documents": ["Project description", "IEE/EIA report"],
     "duration_days": 45, "fee_note": "Applicable to larger projects"},
    {"step": 6, "name": "Commencement certificate", "authority": "Development authority",
     "documents": ["All approvals", "Contractor registration"],
     "duration_days": 10, "fee_note": "—"},
    {"step": 7, "name": "Completion & occupancy certificate", "authority": "Development authority / Civil Defence",
     "documents": ["As-built drawings", "Test certificates", "Fire NOC"],
     "duration_days": 30, "fee_note": "Occupancy fee"},
]


def approval_checklist(project_type: str = "house", city: Optional[str] = None) -> Dict[str, Any]:
    steps = [dict(s) for s in APPROVAL_STEPS]
    skip_environmental = project_type in ("house", "floor", "shop", "space")
    if skip_environmental:
        steps = [s for s in steps if s["name"] != "Environmental screening / EIA"]
    total_days = sum(s["duration_days"] for s in steps)
    return {
        "project_type": project_type, "city": city or CONSTRUCTION_CONFIG["default_city"],
        "authority": "LDA / CDA / KDA / SBCA (as applicable)",
        "steps": steps, "step_count": len(steps),
        "total_approval_days": total_days,
        "note": "Durations run partly in parallel; environmental clearance applies to larger projects.",
    }


QA_CHECKS: Dict[str, List[str]] = {
    "excavation": ["Set out levels verified against drawings", "Soil bearing checked at founding level",
                   "Dewatering provided where water table is high", "Side slopes/shores safe"],
    "foundation": ["PCC thickness and grade as specified", "Reinforcement spacing and cover checked",
                   "Foundation depth below natural ground", "Waterproofing / DPC on top of plinth"],
    "structure": ["Steel grade and diameter as per bar-bending schedule", "Formwork plumb and propped",
                  "Concrete mix ratio / design mix used", "Cube samples taken (7 & 28 days)",
                  "Slump test within limits", "Curing for the required period", "Cover blocks used"],
    "masonry": ["Bricks/blocks soaked and matched to spec", "Mortar ratio as specified",
                "Verticality and line checked", "Lintels/bands provided over openings"],
    "mep": ["Concealed conduits and pipes pressure-tested", "Earthing and DB schedule verified",
            "Waterproofing of wet areas before tiling", "Drainage slopes fall toward outlets"],
    "finishes": ["Levels and slopes verified", "Skirting and joints aligned", "Paint coats as specified",
                 "No hollow patches / cracks"],
    "handover": ["Snag list closed", "All testing certificates collected", "As-built drawings issued",
                 "Warranty documents and O&M manuals handed over"],
}


def qa_checklist(stage: Optional[str] = None) -> Dict[str, Any]:
    if stage and stage in QA_CHECKS:
        return {"stage": stage, "checks": QA_CHECKS[stage]}
    return {"stages": QA_CHECKS, "stage_count": len(QA_CHECKS)}


HSE_RULES: List[Dict[str, str]] = [
    {"key": "ppe", "rule": "Mandatory PPE: helmet, boots, gloves, harness for work at height"},
    {"key": "edge", "rule": "Guard rails and netting on all open edges and lift shafts"},
    {"key": "scaffold", "rule": "Scaffolds tied to the structure, planked and inspected"},
    {"key": "electrical", "rule": "Lock-out/tag-out; no live work; earthing of plant"},
    {"key": "lifting", "rule": "Certified lifting gear; exclusion zones under crane loads"},
    {"key": "excavation", "rule": "Shoring for deep trenches; ladders for access"},
    {"key": "welfare", "rule": "Drinking water, shade, first aid and toilet facilities on site"},
    {"key": "public", "rule": "Hoarding, dust control and safe public diversion"},
    {"key": "housekeeping", "rule": "Daily housekeeping; correct waste segregation"},
    {"key": "incident", "rule": "Report and investigate all incidents; maintain a register"},
]


def hse_rules() -> List[Dict[str, str]]:
    return list(HSE_RULES)


# ============================================================
# MODELS & STORE  (saved estimates / advisory records)
# ============================================================


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


def _m(model: BaseModel) -> Dict[str, Any]:
    return model.model_dump(mode="json")


class ConstructionEstimate(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("ce_"))
    title: str
    building_type: str = "house"
    quality_tier: str = "standard"
    system: str = "rcc_frame"
    city: str = "Lahore"
    covered_area_sqft: float
    floors: int = 1
    plot_area_sqft: Optional[float] = None
    total_cost: float = 0.0
    cost_per_sqft: float = 0.0
    duration_days: int = 0
    notes: Optional[str] = None
    created_at: str = Field(default_factory=_now)


estimates_db: List[ConstructionEstimate] = []


def find_estimate(estimate_id: Optional[str]) -> Optional[ConstructionEstimate]:
    return next((e for e in estimates_db if e.id == estimate_id), None)


def list_estimates(building_type: Optional[str] = None, city: Optional[str] = None) -> List[ConstructionEstimate]:
    rows = list(estimates_db)
    if building_type:
        rows = [e for e in rows if e.building_type == building_type]
    if city:
        rows = [e for e in rows if e.city == city]
    return sorted(rows, key=lambda e: e.created_at, reverse=True)


# ============================================================
# INTELLIGENCE ENGINE
# ============================================================


def format_pkr(amount: float, symbol: str = "Rs") -> str:
    """Compact PKR string: millions / billions for readability."""
    a = float(amount or 0.0)
    if abs(a) >= 1_000_000_000:
        return f"{symbol} {a / 1_000_000_000:,.2f}B"
    if abs(a) >= 1_000_000:
        return f"{symbol} {a / 1_000_000:,.2f}M"
    if abs(a) >= 1_000:
        return f"{symbol} {a / 1_000:,.1f}K"
    return f"{symbol} {a:,.0f}"


def timeline_estimate(covered_area: float, floors: int = 1, building_type: str = "house",
                      system: str = "rcc_frame") -> Dict[str, Any]:
    """Phase-weighted construction timeline in days."""
    bt = BUILDING_TYPES.get(building_type, BUILDING_TYPES["house"])
    system_factor = 1.0
    s = find_system(system)
    if s and s["speed_floors_per_month"]:
        system_factor = max(0.55, min(1.6, 2.0 / s["speed_floors_per_month"]))
    base = (max(covered_area, 1.0) / 1000.0) * bt["days_per_1000sqft"]
    total = int(round(base * system_factor + floors * 12 + 30))
    phases = []
    for ph in CONSTRUCTION_PHASES:
        phases.append({
            "key": ph["key"], "name": ph["name"],
            "days": int(round(total * ph["weight"] / 100.0)),
            "weight_pct": ph["weight"], "depends_on": ph["depends_on"],
        })
    return {"total_days": total, "total_months": round(total / 30.0, 1),
            "system_factor": round(system_factor, 3), "phases": phases}


# Material consumption coefficients per sq-ft of covered area (grey + finishes)
TAKEOFF_COEFF: Dict[str, float] = {
    "cement_opc": 0.42, "steel_60": 3.2, "sand": 2.4, "aggregate": 2.0,
    "brick_a": 12.0, "floor_tile": 1.05, "paint_emulsion": 0.12,
    "waterproof_membrane": 0.22, "pvc_pipe": 0.28, "gi_pipe": 0.22,
    "electrical_wire": 0.95, "aluminium_window": 0.14,
}


def material_takeoff(covered_area: float, quality_tier: str = "standard",
                     building_type: str = "house") -> Dict[str, Any]:
    """Approximate material quantities from covered area with wastage."""
    tier_mult = {"economy": 0.92, "standard": 1.0, "premium": 1.12, "luxury": 1.3}.get(quality_tier, 1.0)
    btype = building_type if building_type in BUILDING_TYPES else "house"
    grey_mult = 1.0 if btype not in ("warehouse", "shed") else 0.8
    lines = []
    total_value = 0.0
    for key, coeff in TAKEOFF_COEFF.items():
        mat = find_material(key)
        if not mat:
            continue
        qty = covered_area * coeff * tier_mult * (grey_mult if mat["category"] in ("binding", "steel", "aggregate", "masonry") else 1.0)
        wastage = qty * mat["wastage_pct"] / 100.0
        gross = qty + wastage
        value = gross * mat["unit_rate"]
        total_value += value
        lines.append({
            "material": key, "name": mat["name"], "unit": mat["unit"],
            "quantity": round(qty, 1), "wastage": round(wastage, 1),
            "quantity_with_wastage": round(gross, 1),
            "unit_rate": mat["unit_rate"], "estimated_cost": round(value, 0),
        })
    return {"building_type": btype, "quality_tier": quality_tier,
            "covered_area_sqft": covered_area, "lines": lines,
            "material_value": round(total_value, 0),
            "note": "Indicative take-off for budgeting; final quantities come from drawings."}


def estimate_construction(
    covered_area: float,
    floors: int = 1,
    building_type: str = "house",
    quality_tier: str = "standard",
    system: str = "rcc_frame",
    city: Optional[str] = None,
    plot_area: Optional[float] = None,
    escalation_years: float = 0.0,
    include_elements: bool = True,
) -> Dict[str, Any]:
    """Full parameterised construction-cost estimate.

    Returns the element-wise build-up, preliminaries/contingency/consultancy,
    contractor overhead & profit, escalation, totals, per-sq-ft rate, timeline
    and an indicative material take-off.
    """
    cfg = CONSTRUCTION_CONFIG
    if building_type not in BUILDING_TYPES:
        return {"error": f"Unknown building_type: {building_type}", "types": sorted(BUILDING_TYPES)}
    if quality_tier not in cfg["quality_base_rate_sqft"]:
        return {"error": f"Unknown quality_tier: {quality_tier}", "tiers": sorted(cfg["quality_base_rate_sqft"])}
    if not find_system(system):
        return {"error": f"Unknown system: {system}", "systems": [s["key"] for s in CONSTRUCTION_SYSTEMS]}
    if covered_area <= 0:
        return {"error": "covered_area must be > 0"}

    city_name = city or cfg["default_city"]
    city_factor = cfg["city_multipliers"].get(city_name, 1.0)
    bt = BUILDING_TYPES[building_type]
    sys_row = find_system(system) or {}
    sys_factor = float(sys_row.get("cost_factor", 1.0))
    floor_factor = 1.0 + cfg["floor_premium_pct"] / 100.0 * max(0, floors - cfg["floor_premium_from"])

    base_rate = cfg["quality_base_rate_sqft"][quality_tier]
    effective_rate = base_rate * bt["factor"] * city_factor * sys_factor * floor_factor
    subtotal = covered_area * effective_rate

    shares = element_shares(building_type, quality_tier)
    elements = []
    for el, pct in sorted(shares.items(), key=lambda kv: -kv[1]):
        amount = subtotal * pct / 100.0
        elements.append({"element": el, "label": ELEMENT_LABELS[el],
                         "category": ELEMENT_CATEGORY[el], "share_pct": round(pct, 2),
                         "amount": round(amount, 0)})

    preliminaries = subtotal * cfg["preliminaries_pct"] / 100.0
    contingency = (subtotal + preliminaries) * cfg["contingency_pct"] / 100.0
    consultancy = subtotal * cfg["consultancy_pct"] / 100.0
    overhead_profit = (subtotal + preliminaries) * cfg["overhead_profit_pct"] / 100.0
    pre_escalation = subtotal + preliminaries + contingency + consultancy + overhead_profit
    escalation = pre_escalation * ((1.0 + cfg["escalation_cagr"]) ** max(0.0, escalation_years) - 1.0) if escalation_years else 0.0
    total = pre_escalation + escalation

    timeline = timeline_estimate(covered_area, floors, building_type, system)
    result: Dict[str, Any] = {
        "inputs": {
            "covered_area_sqft": covered_area, "floors": floors, "building_type": building_type,
            "quality_tier": quality_tier, "system": system, "city": city_name,
            "plot_area_sqft": plot_area, "escalation_years": escalation_years,
        },
        "assumptions": {
            "base_rate_sqft": base_rate, "building_type_factor": bt["factor"],
            "city_factor": city_factor, "system_factor": sys_factor,
            "floor_factor": round(floor_factor, 4), "effective_rate_sqft": round(effective_rate, 2),
        },
        "cost": {
            "subtotal_construction": round(subtotal, 0),
            "preliminaries": round(preliminaries, 0),
            "contingency": round(contingency, 0),
            "consultancy_and_approvals": round(consultancy, 0),
            "contractor_overhead_profit": round(overhead_profit, 0),
            "escalation": round(escalation, 0),
            "total": round(total, 0),
            "cost_per_sqft": round(total / covered_area, 2),
            "total_text": format_pkr(total),
            "cost_per_sqft_text": f"Rs {total / covered_area:,.0f} / sqft",
        },
        "elements": elements if include_elements else [],
        "timeline": timeline,
        "takeoff": material_takeoff(covered_area, quality_tier, building_type),
        "system": {"key": sys_row.get("key"), "name": sys_row.get("name"),
                   "category": sys_row.get("category"), "speed_floors_per_month": sys_row.get("speed_floors_per_month")},
    }
    return result


def compare_systems(
    covered_area: float, floors: int = 1, building_type: str = "house",
    quality_tier: str = "standard", city: Optional[str] = None,
    category: str = "structure",
) -> Dict[str, Any]:
    """Compare construction techniques by cost and speed for one building."""
    rows = []
    for s in construction_systems(category):
        est = estimate_construction(covered_area, floors, building_type, quality_tier,
                                    system=s["key"], city=city, include_elements=False)
        if "error" in est:
            continue
        rows.append({
            "system": s["key"], "name": s["name"],
            "total": est["cost"]["total"], "cost_per_sqft": est["cost"]["cost_per_sqft"],
            "duration_days": est["timeline"]["total_days"],
            "speed_floors_per_month": s["speed_floors_per_month"],
            "cost_factor": s["cost_factor"],
            "ecg": s["sustainability"], "seismic_rating": s["seismic_rating"],
        })
    rows.sort(key=lambda r: r["total"])
    cheapest = rows[0]["total"] if rows else 0.0
    for r in rows:
        r["vs_cheapest_pct"] = round((r["total"] - cheapest) / cheapest * 100, 1) if cheapest else 0.0
    return {"building_type": building_type, "quality_tier": quality_tier, "covered_area_sqft": covered_area,
            "floors": floors, "category": category, "count": len(rows),
            "cheapest": rows[0]["system"] if rows else None,
            "fastest": min(rows, key=lambda r: r["duration_days"])["system"] if rows else None,
            "options": rows}


def construction_impact(
    covered_area: float, building_type: str = "house", city: Optional[str] = None,
    from_tier: str = "standard", to_tier: str = "premium",
    market_rate_sqft: float = 12000.0, gross_yield: float = 0.05, floors: int = 1,
) -> Dict[str, Any]:
    """How upgrading the construction quality moves value, cost and payback."""
    VALUE_PREMIUM = {"economy": 0.0, "standard": 0.045, "premium": 0.10, "luxury": 0.17}
    base = estimate_construction(covered_area, floors, building_type, from_tier, city=city, include_elements=False)
    up = estimate_construction(covered_area, floors, building_type, to_tier, city=city, include_elements=False)
    if "error" in base or "error" in up:
        return {"error": "Invalid tier(s)", "tiers": sorted(VALUE_PREMIUM)}
    extra_cost = up["cost"]["total"] - base["cost"]["total"]
    market_value = covered_area * market_rate_sqft
    value_uplift = market_value * (VALUE_PREMIUM.get(to_tier, 0.0) - VALUE_PREMIUM.get(from_tier, 0.0))
    rent_uplift_annual = value_uplift * gross_yield
    net_gain = value_uplift - extra_cost
    payback_years = round(extra_cost / rent_uplift_annual, 1) if rent_uplift_annual > 0 else None
    return {
        "from_tier": from_tier, "to_tier": to_tier, "covered_area_sqft": covered_area,
        "base_cost": base["cost"]["total"], "upgraded_cost": up["cost"]["total"],
        "extra_cost": round(extra_cost, 0), "extra_cost_text": format_pkr(extra_cost),
        "market_value": round(market_value, 0),
        "value_uplift": round(value_uplift, 0), "value_uplift_text": format_pkr(value_uplift),
        "rent_uplift_annual": round(rent_uplift_annual, 0),
        "net_gain": round(net_gain, 0), "net_gain_text": format_pkr(net_gain),
        "payback_years": payback_years,
        "roi_pct": round(net_gain / extra_cost * 100, 1) if extra_cost else 0.0,
        "verdict": "worth it" if net_gain > 0 else "marginal",
        "maintenance_note": "Higher build quality lowers future maintenance and tends to raise occupancy.",
    }


def construction_advisory(
    plot_area: float, floors: int = 2, building_type: str = "house",
    city: Optional[str] = None, soil: str = "sandy_loam", seismic_zone: str = "2A",
    budget_per_sqft: Optional[float] = None,
) -> Dict[str, Any]:
    """Recommend technique + foundation + guidelines for a site."""
    soil_row = SOIL_TYPES.get(soil, SOIL_TYPES["sandy_loam"])
    zone_row = SEISMIC_ZONES.get(str(seismic_zone), SEISMIC_ZONES["2A"])
    suitable = []
    for s in construction_systems("structure"):
        if floors < s["min_floors"] or floors > s["max_floors"]:
            continue
        if building_type not in s["suitable_for"]:
            continue
        if soil not in s["soil_suitability"] and "any" not in s["soil_suitability"]:
            continue
        suitable.append(s)
    rec = suitable[0]["key"] if suitable else "rcc_frame"
    guided = guidelines(building_type=building_type)
    return {
        "inputs": {"plot_area_sqft": plot_area, "floors": floors, "building_type": building_type,
                   "city": city or CONSTRUCTION_CONFIG["default_city"], "soil": soil,
                   "seismic_zone": str(seismic_zone), "budget_per_sqft": budget_per_sqft},
        "soil": {"key": soil, **soil_row},
        "seismic_zone": {"key": str(seismic_zone), **zone_row},
        "recommended_system": rec,
        "suitable_systems": [{"key": s["key"], "name": s["name"], "cost_factor": s["cost_factor"],
                              "speed_floors_per_month": s["speed_floors_per_month"],
                              "seismic_rating": s["seismic_rating"]} for s in suitable],
        "foundation_recommendation": soil_row["foundation"],
        "guidelines": [{"key": g["key"], "title": g["title"], "category": g["category"],
                        "authority": g["authority"]} for g in guided],
        "safety": hse_rules()[:5],
    }


def construction_overview() -> Dict[str, Any]:
    """Counts and breakdowns for the whole construction wing."""
    def _tally(vals: Any) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for v in vals:
            out[v] = out.get(v, 0) + 1
        return out
    return {
        "config": CONSTRUCTION_CONFIG,
        "counts": {
            "systems": len(CONSTRUCTION_SYSTEMS), "materials": len(MATERIALS),
            "element_rates": len(ELEMENT_RATES), "phases": len(CONSTRUCTION_PHASES),
            "trades": len(TRADES), "guidelines": len(CONSTRUCTION_GUIDELINES),
            "approval_steps": len(APPROVAL_STEPS), "qa_stages": len(QA_CHECKS),
            "hse_rules": len(HSE_RULES), "saved_estimates": len(estimates_db),
        },
        "systems_by_category": _tally(s["category"] for s in CONSTRUCTION_SYSTEMS),
        "materials_by_category": _tally(m["category"] for m in MATERIALS),
        "building_types": {k: v["label"] for k, v in BUILDING_TYPES.items()},
        "quality_tiers": CONSTRUCTION_CONFIG["quality_labels"],
        "guidelines_by_category": _tally(g["category"] for g in CONSTRUCTION_GUIDELINES),
        "cities": list(CONSTRUCTION_CONFIG["city_multipliers"]),
    }


def save_estimate(est: Dict[str, Any], title: str, notes: Optional[str] = None) -> ConstructionEstimate:
    """Persist an estimate result as a stored record (used by the seeds/API)."""
    inp = est.get("inputs", {})
    rec = ConstructionEstimate(
        title=title, building_type=inp.get("building_type", "house"),
        quality_tier=inp.get("quality_tier", "standard"), system=inp.get("system", "rcc_frame"),
        city=inp.get("city", CONSTRUCTION_CONFIG["default_city"]),
        covered_area_sqft=inp.get("covered_area_sqft", 0.0), floors=inp.get("floors", 1),
        plot_area_sqft=inp.get("plot_area_sqft"),
        total_cost=est.get("cost", {}).get("total", 0.0),
        cost_per_sqft=est.get("cost", {}).get("cost_per_sqft", 0.0),
        duration_days=est.get("timeline", {}).get("total_days", 0), notes=notes,
    )
    estimates_db.append(rec)
    return rec


def estimate_view(rec: ConstructionEstimate) -> Dict[str, Any]:
    view = _m(rec)
    view["budget_text"] = format_pkr(rec.total_cost)
    view["type_label"] = BUILDING_TYPES.get(rec.building_type, {}).get("label", rec.building_type)
    view["tier_label"] = CONSTRUCTION_CONFIG["quality_labels"].get(rec.quality_tier, rec.quality_tier)
    return view
