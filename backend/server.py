"""
Real Estate Portal — MCP Server (single source of truth)
========================================================

Hierarchical real-estate portal exposed over the Model Context Protocol.

Structure
---------
City -> Housing Scheme -> Block/Zone/Area -> Property
Plus Big Projects (mall / tower / mixed-use / compound / plaza / office complex)
Plus a CRM layer (agents, leads, customers, deals, tasks, appointments, interactions)

Capabilities
------------
* Hierarchy CRUD + search
* GIS: coordinates, Haversine distance, nearby search
* Pakistani measurement units (Marla / Kanal / SqFt / SqYd)
* Memory layers: near-memory cache + long-term memory
* RAG: natural-language retrieval over the whole catalogue
* Investment analysis + market insights
* Big-project entities with maps / floor plans / amenities / multimedia
* Image library for every entity
* CRM (leads -> customers -> deals pipeline)
* Full double-entry accounting + investment maths (ROI / IRR / NPV / mortgage)
* GIS points of interest (POI) and saved areas of interest (AOI)
* FastAPI integration metadata

The same business functions registered here as MCP tools are plain Python
functions, so `api.py` (FastAPI) and `test_integration.py` reuse them directly.

Run the MCP server (stdio + Inspector):
    uv run mcp dev server.py

Run the combined FastAPI + MCP HTTP app:
    uv run python main.py
"""

import json
import math
import os
import re
import statistics
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from mcp.server.mcpserver import MCPServer

import accounting
import agents
import auth
import commercial
import construction
import content
import geo
import masterplan
import gis
import intelligence
import leasing
import maintenance
import marketing
import messaging
import pmo
import tools
import transactions

# ============================================================
# SERVER
# ============================================================

mcp = MCPServer("RealEstatePortal")

SERVER_VERSION = "2.0.0"


# ============================================================
# DATABASE ABSTRACTION LAYER
# ============================================================


class DatabaseConfig:
    """Configuration for the storage backend (in-memory now, PostgreSQL later)."""

    use_postgres: bool = False
    postgres_url: str = "postgresql://localhost/real_estate"
    sqlite_path: str = "real_estate.db"


db_config = DatabaseConfig()


# ============================================================
# DATA MODELS
# ============================================================


class MediaMixin(BaseModel):
    """Media/document fields shared by every entity."""

    image_urls: List[str] = Field(default_factory=list)  # photos / renderings
    maps: List[str] = Field(default_factory=list)  # maps, satellite images
    floor_plans: List[str] = Field(default_factory=list)  # floor / layout plans
    image_library: List[str] = Field(default_factory=list)  # full gallery
    amenities: List[str] = Field(default_factory=list)  # amenity list
    multimedia: Dict[str, Any] = Field(default_factory=dict)  # video / VR / drone


class City(MediaMixin):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    state: Optional[str] = None
    country: str = "Pakistan"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class HousingScheme(MediaMixin):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: Optional[str] = None
    city_id: str
    total_units: Optional[int] = None
    established_year: Optional[int] = None
    developer: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    # Development details (entered by staff; the assistant adds map-based estimates).
    development_status: Optional[str] = None   # e.g. developed, under development, planned
    approval_authority: Optional[str] = None   # e.g. RDA, CDA, LDA, KDA
    possession_status: Optional[str] = None    # e.g. possession given, partial, not yet
    utilities: List[str] = Field(default_factory=list)  # electricity, gas, water, sewerage …
    population: Optional[int] = None           # residents, if the society publishes it
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class BlockZoneArea(MediaMixin):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: Optional[str] = None
    scheme_id: str
    area_type: str = "residential"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class Property(MediaMixin):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: Optional[str] = None
    price: float
    currency: str = "PKR"
    use_type: str = "residential"  # residential | commercial | mix
    category: str = "house"  # plot | house | building | apartment | office | shop | floor | space | warehouse | shed
    status: str = "active"  # active | sold | rented | pending
    featured: bool = False

    # Area (sq ft canonical; Pakistani units kept in sync)
    total_area: Optional[float] = None
    covered_area: Optional[float] = None
    plot_area: Optional[float] = None
    marla_area: Optional[float] = None
    kanal_area: Optional[float] = None

    # Hierarchy
    city_id: str
    scheme_id: Optional[str] = None
    block_zone_area_id: Optional[str] = None

    # Detail
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    balconies: Optional[int] = None
    floors: Optional[int] = None

    # Address / location
    street_address: Optional[str] = None
    plot_number: Optional[str] = None
    sector: Optional[str] = None
    landmark: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    geo_json: Optional[str] = None

    agent_id: Optional[str] = None
    owner_user_id: Optional[str] = None  # portal account that published the listing
    available_from: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


# Big-project types
PROJECT_TYPE_MALL = "mall"
PROJECT_TYPE_TOWER = "tower"
PROJECT_TYPE_MIXED_USE = "mixed_use"
PROJECT_TYPE_COMPOUND_LIVING = "compound_living"
PROJECT_TYPE_PLAZA = "plaza"
PROJECT_TYPE_OFFICE_COMPLEX = "office_complex"
PROJECT_TYPE_RESIDENTIAL_COMPLEX = "residential_complex"


class BigProject(MediaMixin):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: Optional[str] = None
    project_type: str = PROJECT_TYPE_MALL
    status: str = "planned"  # planned | under_construction | completed
    floor_count: int = 0
    total_area: Optional[float] = None
    total_units: Optional[int] = None
    occupancy_rate: Optional[float] = None

    city_id: str
    scheme_id: Optional[str] = None
    block_zone_area_id: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    developer: Optional[str] = None
    start_date: Optional[str] = None
    completion_date: Optional[str] = None
    leased_units: Optional[int] = None
    total_parking_spaces: Optional[int] = None
    total_retail_space: Optional[float] = None
    total_office_space: Optional[float] = None
    total_residential_units: Optional[int] = None

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


# ============================================================
# CRM MODELS
# ============================================================

LEAD_STATUSES = ["new", "contacted", "qualified", "proposal", "negotiation", "won", "lost"]
DEAL_STAGES = ["prospecting", "qualification", "proposal", "negotiation", "contract", "closed_won", "closed_lost"]
TASK_PRIORITIES = ["low", "medium", "high", "urgent"]
TASK_STATUSES = ["open", "in_progress", "done", "cancelled"]


class Agent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    region: Optional[str] = None
    specialization: Optional[str] = None  # residential | commercial | investment ...
    active: bool = True
    rating: float = 0.0
    deals_closed: int = 0
    commission_rate: float = 0.02
    created_at: datetime = Field(default_factory=datetime.now)


class Lead(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    source: str = "website"  # website | referral | walk_in | call | portal ...
    status: str = "new"
    score: int = 0  # 0-100

    # interest
    interest_use_type: Optional[str] = None
    interest_category: Optional[str] = None
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    city_id: Optional[str] = None
    scheme_id: Optional[str] = None

    assigned_agent_id: Optional[str] = None
    notes: Optional[str] = None
    converted_customer_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class Customer(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    type: str = "buyer"  # buyer | seller | investor | tenant | landlord
    city_id: Optional[str] = None
    source_lead_id: Optional[str] = None
    assigned_agent_id: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class Interaction(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    entity_type: str = "lead"  # lead | customer | deal
    entity_id: str
    channel: str = "call"  # call | email | meeting | whatsapp | site_visit | sms
    direction: str = "outbound"
    summary: str = ""
    agent_id: Optional[str] = None
    occurred_at: datetime = Field(default_factory=datetime.now)


class Deal(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    lead_id: Optional[str] = None
    customer_id: Optional[str] = None
    property_id: Optional[str] = None
    agent_id: Optional[str] = None
    amount: float = 0.0
    currency: str = "PKR"
    stage: str = "prospecting"
    probability: int = 20  # 0-100
    commission: float = 0.0
    expected_close_date: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class Task(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: Optional[str] = None
    assigned_agent_id: Optional[str] = None
    related_type: Optional[str] = None  # lead | customer | deal | property
    related_id: Optional[str] = None
    due_date: Optional[str] = None
    priority: str = "medium"
    status: str = "open"
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class Appointment(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    lead_id: Optional[str] = None
    customer_id: Optional[str] = None
    property_id: Optional[str] = None
    agent_id: Optional[str] = None
    scheduled_at: str = ""
    status: str = "scheduled"  # scheduled | completed | cancelled | no_show
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)


# ============================================================
# MARKET INTELLIGENCE MODELS  (news + factor scores)
# ============================================================

NEWS_CATEGORIES = [
    "macro",  # interest rates, inflation, GDP, currency
    "policy",  # government policy, taxation, amnesty
    "regulation",  # RERA, LDA/CDA approvals, building bylaws
    "market",  # prices, demand, transactions
    "development",  # new societies, projects, master plans
    "infrastructure",  # roads, metro, ring roads, utilities
    "political",  # elections, instability, governance
    "social",  # population, migration, urbanisation, education
    "finance",  # mortgage, bank lending, REITs, overseas remittances
]

NEWS_CHANNEL_TYPES = ["news", "regulator", "government", "developer", "research", "bank"]

SENTIMENTS = ["positive", "neutral", "negative"]


class NewsItem(BaseModel):
    """A news / announcement item that can impact real-estate sentiment."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    source: str  # channel, e.g. "Dawn", "Business Recorder", "SBP", "LDA"
    channel_type: str = "news"  # news | regulator | government | developer | research | bank
    category: str = "market"
    sentiment: str = "neutral"  # positive | neutral | negative
    impact_score: float = 0.0  # -100 (very negative) .. +100 (very positive)
    summary: Optional[str] = None
    url: Optional[str] = None
    city_id: Optional[str] = None
    scheme_id: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    published_at: datetime = Field(default_factory=datetime.now)
    created_at: datetime = Field(default_factory=datetime.now)


class MarketFactor(BaseModel):
    """Qualitative factor scores (0-100) driving the real-estate outlook of a scope."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    scope_type: str = "city"  # national | city | scheme
    scope_id: str
    development_score: float = 60.0  # ongoing / planned development activity
    infrastructure_score: float = 60.0  # roads, utilities, transit
    economic_score: float = 60.0  # income, jobs, growth, mortgages
    social_score: float = 60.0  # population growth, urbanisation, liveability
    political_score: float = 60.0  # stability, governance, policy continuity
    regulatory_score: float = 60.0  # approvals, titling, ease of transaction
    demand_score: float = 60.0  # current absorption / demand momentum
    notes: Optional[str] = None
    updated_at: datetime = Field(default_factory=datetime.now)


FACTOR_WEIGHTS: Dict[str, float] = {
    "development": 0.20,
    "infrastructure": 0.16,
    "economic": 0.20,
    "social": 0.12,
    "political": 0.14,
    "regulatory": 0.10,
    "demand": 0.08,
}

SCENARIOS: Dict[str, Dict[str, Any]] = {
    "optimistic": {"label": "Optimistic", "cagr_delta": 0.045, "cost_multiplier": 1.08, "probability": 0.25},
    "base": {"label": "Base", "cagr_delta": 0.0, "cost_multiplier": 1.0, "probability": 0.50},
    "pessimistic": {"label": "Pessimistic", "cagr_delta": -0.055, "cost_multiplier": 1.12, "probability": 0.20},
    "stress": {"label": "Stress", "cagr_delta": -0.140, "cost_multiplier": 1.20, "probability": 0.05},
}

BASE_PRICE_CAGR = 0.075  # long-run base appreciation before factor/news adjustment
GROWTH_SENSITIVITY = 0.11  # how strongly the composite index swings the CAGR
COST_INFLATION_CAGR = 0.08  # construction/infrastructure cost inflation
DEFAULT_BUILD_YEARS = 3  # assumed development period
LAND_COST_SHARE = 0.30  # share of GDV used as land cost when no plot listings exist


# ============================================================
# IN-MEMORY STORES
# ============================================================

cities_db: List[City] = []
housing_schemes_db: List[HousingScheme] = []
block_zone_areas_db: List[BlockZoneArea] = []
properties_db: List[Property] = []
big_projects_db: List[BigProject] = []

agents_db: List[Agent] = []
leads_db: List[Lead] = []
customers_db: List[Customer] = []
interactions_db: List[Interaction] = []
deals_db: List[Deal] = []
tasks_db: List[Task] = []
appointments_db: List[Appointment] = []

news_db: List[NewsItem] = []
factors_db: List[MarketFactor] = []

# entity_id -> list of {url, description, is_primary, added_at}
image_storage: Dict[str, Dict[str, List[Dict[str, Any]]]] = {
    "city": {},
    "scheme": {},
    "block": {},
    "property": {},
    "bigproject": {},
    "agent": {},
}


# ============================================================
# PAKISTANI MEASUREMENT UNITS
# ============================================================

MARLA_TO_SQFT = 272.25
KANAL_TO_SQFT = 5445.0  # 1 kanal = 20 marla
KANAL_TO_MARLA = 20
SQYD_TO_SQFT = 9.0


def sqft_to_marla(sqft: float) -> float:
    return round(sqft / MARLA_TO_SQFT, 3)


def marla_to_sqft(marla: float) -> float:
    return round(marla * MARLA_TO_SQFT, 2)


def sqft_to_kanal(sqft: float) -> float:
    return round(sqft / KANAL_TO_SQFT, 4)


def kanal_to_sqft(kanal: float) -> float:
    return round(kanal * KANAL_TO_SQFT, 2)


_AREA_UNITS = {
    "sqft": 1.0,
    "sqm": 10.7639,
    "sqyd": SQYD_TO_SQFT,
    "marla": MARLA_TO_SQFT,
    "kanal": KANAL_TO_SQFT,
    "acre": 43560.0,
}


def convert_area_value(value: float, from_unit: str, to_unit: str) -> Optional[float]:
    """Convert between area units. Returns None for unknown units."""
    f = _AREA_UNITS.get(from_unit.lower())
    t = _AREA_UNITS.get(to_unit.lower())
    if f is None or t is None:
        return None
    return round(value * f / t, 4)


# ============================================================
# MEMORY LAYERS
# ============================================================

near_memory_cache: List[Dict[str, Any]] = []
MAX_NEAR_MEMORY_SIZE = 30
long_term_memory: Dict[str, Any] = {
    "search_history": [],
    "property_views": {},
    "favorites": [],
    "preferences": {},
}


# ============================================================
# SERIALISATION HELPERS
# ============================================================


def dump(obj: Any) -> str:
    return json.dumps(obj, default=str, indent=2, ensure_ascii=False)


def dump_model(model: BaseModel) -> str:
    return json.dumps(model.model_dump(mode="json"), indent=2, ensure_ascii=False)


def model_dict(model: BaseModel) -> Dict[str, Any]:
    return model.model_dump(mode="json")


# ============================================================
# LOOKUP HELPERS
# ============================================================


def find_city(city_id: Optional[str]) -> Optional[City]:
    return next((c for c in cities_db if c.id == city_id), None)


def city_name(city_id: Optional[str]) -> str:
    c = find_city(city_id)
    return c.name if c else "Unknown"


def find_scheme(scheme_id: Optional[str]) -> Optional[HousingScheme]:
    return next((s for s in housing_schemes_db if s.id == scheme_id), None)


def find_block(block_id: Optional[str]) -> Optional[BlockZoneArea]:
    return next((b for b in block_zone_areas_db if b.id == block_id), None)


def find_property(property_id: str) -> Optional[Property]:
    return next((p for p in properties_db if p.id == property_id), None)


def find_project(project_id: str) -> Optional[BigProject]:
    return next((p for p in big_projects_db if p.id == project_id), None)


def resolve_city(value: Optional[str]) -> Optional[City]:
    """Resolve a city by id or (case-insensitive) name."""
    if not value:
        return None
    return find_city(value) or next((c for c in cities_db if c.name.lower() == value.lower()), None)


def resolve_scheme(value: Optional[str]) -> Optional[HousingScheme]:
    if not value:
        return None
    return find_scheme(value) or next(
        (s for s in housing_schemes_db if s.name.lower() == value.lower()), None
    )


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in kilometres."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return round(2 * r * math.asin(math.sqrt(a)), 3)


def derive_areas(p: Property) -> None:
    """Keep total_area / marla_area / kanal_area consistent."""
    if p.marla_area is None and p.kanal_area is not None:
        p.marla_area = round(p.kanal_area * KANAL_TO_MARLA, 3)
    if p.kanal_area is None and p.marla_area is not None:
        p.kanal_area = round(p.marla_area / KANAL_TO_MARLA, 4)
    if p.total_area is None:
        if p.marla_area is not None:
            p.total_area = marla_to_sqft(p.marla_area)
        elif p.kanal_area is not None:
            p.total_area = kanal_to_sqft(p.kanal_area)
    if p.total_area and p.marla_area is None:
        p.marla_area = sqft_to_marla(p.total_area)


def remember(kind: str, value: Any) -> None:
    """Push something into the near-memory cache (bounded ring)."""
    near_memory_cache.append({"kind": kind, "value": value, "at": datetime.now().isoformat()})
    if len(near_memory_cache) > MAX_NEAR_MEMORY_SIZE:
        del near_memory_cache[0 : len(near_memory_cache) - MAX_NEAR_MEMORY_SIZE]


def validate_image_url(url: str) -> bool:
    if not url:
        return False
    valid_extensions = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg")
    return any(url.lower().split("?")[0].endswith(ext) for ext in valid_extensions)


# ============================================================
# ==================== MCP TOOLS =============================
# ============================================================

# ---------- Hierarchy: read ----------


@mcp.tool()
def list_cities() -> str:
    """List every city in the portal with its coordinates and child counts."""
    out = []
    for c in cities_db:
        schemes = [s for s in housing_schemes_db if s.city_id == c.id]
        props = [p for p in properties_db if p.city_id == c.id]
        out.append(
            {
                "id": c.id,
                "name": c.name,
                "state": c.state,
                "latitude": c.latitude,
                "longitude": c.longitude,
                "schemes": len(schemes),
                "properties": len(props),
            }
        )
    return dump({"count": len(out), "cities": out})


@mcp.tool()
def list_schemes(city: Optional[str] = None) -> str:
    """List housing schemes/societies, optionally filtered by city (id or name)."""
    c = resolve_city(city) if city else None
    out = []
    for s in housing_schemes_db:
        if c and s.city_id != c.id:
            continue
        out.append(
            {
                "id": s.id,
                "name": s.name,
                "city": city_name(s.city_id),
                "total_units": s.total_units,
                "established_year": s.established_year,
                "development_status": s.development_status,
                "approval_authority": s.approval_authority,
                "blocks": len([b for b in block_zone_areas_db if b.scheme_id == s.id]),
            }
        )
    return dump({"count": len(out), "schemes": out})


@mcp.tool()
def list_blocks(scheme: Optional[str] = None) -> str:
    """List blocks/zones/areas, optionally filtered by scheme (id or name)."""
    s = resolve_scheme(scheme) if scheme else None
    out = []
    for b in block_zone_areas_db:
        if s and b.scheme_id != s.id:
            continue
        out.append(
            {
                "id": b.id,
                "name": b.name,
                "scheme": (find_scheme(b.scheme_id).name if find_scheme(b.scheme_id) else None),
                "area_type": b.area_type,
            }
        )
    return dump({"count": len(out), "blocks": out})


@mcp.tool()
def get_hierarchy() -> str:
    """Return the full City -> Scheme -> Block -> Property tree with counts."""
    tree = []
    for c in cities_db:
        schemes = []
        for s in housing_schemes_db:
            if s.city_id != c.id:
                continue
            blocks = []
            for b in block_zone_areas_db:
                if b.scheme_id != s.id:
                    continue
                blocks.append(
                    {
                        "id": b.id,
                        "name": b.name,
                        "area_type": b.area_type,
                        "properties": len([p for p in properties_db if p.block_zone_area_id == b.id]),
                    }
                )
            schemes.append(
                {
                    "id": s.id,
                    "name": s.name,
                    "blocks": blocks,
                    "properties": len([p for p in properties_db if p.scheme_id == s.id]),
                }
            )
        tree.append({"id": c.id, "name": c.name, "schemes": schemes})
    return dump({"tree": tree})


@mcp.tool()
def get_city_details(city: str) -> str:
    """Get a single city's full record plus its schemes and property count."""
    c = resolve_city(city)
    if not c:
        return dump({"error": f"City not found: {city}"})
    schemes = [model_dict(s) for s in housing_schemes_db if s.city_id == c.id]
    props = [p for p in properties_db if p.city_id == c.id]
    return dump(
        {
            "city": model_dict(c),
            "schemes": schemes,
            "property_count": len(props),
            "big_projects": len([p for p in big_projects_db if p.city_id == c.id]),
        }
    )


# ---------- Hierarchy: write ----------


@mcp.tool()
def add_city(
    name: str,
    state: Optional[str] = None,
    country: str = "Pakistan",
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    description: Optional[str] = None,
) -> str:
    """Create a city."""
    c = City(
        name=name,
        state=state,
        country=country,
        latitude=latitude,
        longitude=longitude,
        description=description,
    )
    cities_db.append(c)
    return dump_model(c)


@mcp.tool()
def add_housing_scheme(
    name: str,
    city_id: str,
    description: Optional[str] = None,
    total_units: Optional[int] = None,
    established_year: Optional[int] = None,
    developer: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    development_status: Optional[str] = None,
    approval_authority: Optional[str] = None,
    possession_status: Optional[str] = None,
    utilities: Optional[List[str]] = None,
    population: Optional[int] = None,
) -> str:
    """Create a housing scheme/society inside a city (with optional development details)."""
    if not find_city(city_id):
        return dump({"error": f"City not found: {city_id}"})
    s = HousingScheme(
        name=name,
        city_id=city_id,
        description=description,
        total_units=total_units,
        established_year=established_year,
        developer=developer,
        latitude=latitude,
        longitude=longitude,
        development_status=development_status,
        approval_authority=approval_authority,
        possession_status=possession_status,
        utilities=utilities or [],
        population=population,
    )
    housing_schemes_db.append(s)
    return dump_model(s)


@mcp.tool()
def update_housing_scheme(
    scheme_id: str,
    description: Optional[str] = None,
    total_units: Optional[int] = None,
    established_year: Optional[int] = None,
    developer: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    development_status: Optional[str] = None,
    approval_authority: Optional[str] = None,
    possession_status: Optional[str] = None,
    utilities: Optional[List[str]] = None,
    population: Optional[int] = None,
) -> str:
    """Update a housing scheme's details, e.g. its development / approval / possession status."""
    s = find_scheme(scheme_id) or resolve_scheme(scheme_id)
    if not s:
        return dump({"error": f"Housing scheme not found: {scheme_id}"})
    fields = {
        "description": description, "total_units": total_units, "established_year": established_year,
        "developer": developer, "latitude": latitude, "longitude": longitude,
        "development_status": development_status, "approval_authority": approval_authority,
        "possession_status": possession_status, "utilities": utilities, "population": population,
    }
    for key, value in fields.items():
        if value is not None:
            setattr(s, key, value)
    s.updated_at = datetime.now()
    return dump_model(s)


@mcp.tool()
def add_block_zone_area(
    name: str,
    scheme_id: str,
    description: Optional[str] = None,
    area_type: str = "residential",
) -> str:
    """Create a block/zone/area inside a housing scheme."""
    if not find_scheme(scheme_id):
        return dump({"error": f"Scheme not found: {scheme_id}"})
    b = BlockZoneArea(name=name, scheme_id=scheme_id, description=description, area_type=area_type)
    block_zone_areas_db.append(b)
    return dump_model(b)


# ---------- Properties ----------


@mcp.tool()
def add_property(
    title: str,
    price: float,
    city_id: str,
    description: Optional[str] = None,
    use_type: str = "residential",
    category: str = "house",
    scheme_id: Optional[str] = None,
    block_zone_area_id: Optional[str] = None,
    total_area: Optional[float] = None,
    marla_area: Optional[float] = None,
    kanal_area: Optional[float] = None,
    bedrooms: Optional[int] = None,
    bathrooms: Optional[int] = None,
    balconies: Optional[int] = None,
    floors: Optional[int] = None,
    street_address: Optional[str] = None,
    plot_number: Optional[str] = None,
    sector: Optional[str] = None,
    landmark: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    featured: bool = False,
    agent_id: Optional[str] = None,
    owner_user_id: Optional[str] = None,
    amenities: Optional[List[str]] = None,
) -> str:
    """Create a property. Areas auto-derive between total_area / marla / kanal."""
    if not find_city(city_id):
        return dump({"error": f"City not found: {city_id}"})
    p = Property(
        title=title,
        description=description,
        price=price,
        city_id=city_id,
        use_type=use_type,
        category=category,
        scheme_id=scheme_id,
        block_zone_area_id=block_zone_area_id,
        total_area=total_area,
        marla_area=marla_area,
        kanal_area=kanal_area,
        bedrooms=bedrooms,
        bathrooms=bathrooms,
        balconies=balconies,
        floors=floors,
        street_address=street_address,
        plot_number=plot_number,
        sector=sector,
        landmark=landmark,
        latitude=latitude,
        longitude=longitude,
        featured=featured,
        agent_id=agent_id,
        owner_user_id=owner_user_id,
        amenities=_clean_amenities(amenities),
    )
    derive_areas(p)
    properties_db.append(p)
    return dump_model(p)


def _clean_amenities(items: Optional[List[str]]) -> List[str]:
    """Trimmed, de-duplicated amenity names (case-insensitive), at most 30."""
    seen: Dict[str, str] = {}
    for item in items or []:
        name = " ".join(str(item).split())[:60]
        if name and name.lower() not in seen:
            seen[name.lower()] = name
    return list(seen.values())[:30]


@mcp.tool()
def list_owned_properties(owner_user_id: str, status: Optional[str] = None, limit: int = 100) -> str:
    """List the properties a portal account has published (newest first)."""
    owned = [p for p in properties_db if p.owner_user_id == owner_user_id
             and (not status or p.status.lower() == status.lower())]
    owned.sort(key=lambda p: p.created_at, reverse=True)
    payload = []
    for p in owned[: max(0, limit)]:
        d = model_dict(p)
        d["city_name"] = city_name(p.city_id)
        payload.append(d)
    return dump({"count": len(owned), "returned": len(payload), "results": payload})


@mcp.tool()
def get_property_by_id(property_id: str) -> str:
    """Fetch one property, including its hierarchy context and neighbours."""
    p = find_property(property_id)
    if not p:
        return dump({"error": f"Property not found: {property_id}"})
    long_term_memory["property_views"][property_id] = long_term_memory["property_views"].get(property_id, 0) + 1
    remember("property_view", property_id)
    data = model_dict(p)
    data["city_name"] = city_name(p.city_id)
    s = find_scheme(p.scheme_id)
    data["scheme_name"] = s.name if s else None
    b = find_block(p.block_zone_area_id)
    data["block_name"] = b.name if b else None
    data["price_per_sqft"] = round(p.price / p.total_area, 2) if p.total_area else None
    return dump(data)


@mcp.tool()
def update_property(
    property_id: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    price: Optional[float] = None,
    use_type: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    bedrooms: Optional[int] = None,
    bathrooms: Optional[int] = None,
    total_area: Optional[float] = None,
    marla_area: Optional[float] = None,
    kanal_area: Optional[float] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    featured: Optional[bool] = None,
    amenities: Optional[List[str]] = None,
) -> str:
    """Update editable fields of a property (only the provided fields change)."""
    p = find_property(property_id)
    if not p:
        return dump({"error": f"Property not found: {property_id}"})
    fields = {
        "title": title,
        "description": description,
        "price": price,
        "use_type": use_type,
        "category": category,
        "status": status,
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "total_area": total_area,
        "marla_area": marla_area,
        "kanal_area": kanal_area,
        "latitude": latitude,
        "longitude": longitude,
        "featured": featured,
        "amenities": _clean_amenities(amenities) if amenities is not None else None,
    }
    for key, value in fields.items():
        if value is not None:
            setattr(p, key, value)
    derive_areas(p)
    p.updated_at = datetime.now()
    return dump_model(p)


@mcp.tool()
def delete_property(property_id: str) -> str:
    """Delete a property by id."""
    p = find_property(property_id)
    if not p:
        return dump({"error": f"Property not found: {property_id}"})
    properties_db.remove(p)
    image_storage["property"].pop(property_id, None)
    return dump({"deleted": True, "property_id": property_id, "remaining": len(properties_db)})


@mcp.tool()
def search_properties(
    city: Optional[str] = None,
    scheme: Optional[str] = None,
    use_type: Optional[str] = None,
    category: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    bedrooms: Optional[int] = None,
    min_marla: Optional[float] = None,
    max_marla: Optional[float] = None,
    featured: Optional[bool] = None,
    status: Optional[str] = None,
    limit: int = 20,
    min_bathrooms: Optional[int] = None,
    feature: Optional[str] = None,
    near: Optional[str] = None,
    near_km: float = 2.0,
    near_place: Optional[str] = None,
) -> str:
    """Search properties with hierarchical and numeric filters.

    ``feature`` matches the listing's own amenities / description (e.g. "solar",
    "basement", "pool"). ``near`` keeps listings with that kind of place within
    ``near_km`` (school, mosque, hospital, mall, market, park, bank, restaurant,
    transport, fuel — or a POI category). ``near_place`` keeps listings within
    ``near_km`` of a named place or area ("Rawalpindi Medical University", "G-13");
    when none are that close, the nearest ones are returned as ``nearest_outside_radius``."""
    c = resolve_city(city) if city else None
    s = resolve_scheme(scheme) if scheme else None
    near_cat = NEAR_CATEGORIES.get(near.strip().lower(), near.strip().lower()) if near else None
    feature_q = feature.strip().lower() if feature else None
    near_hits: Dict[str, Dict[str, Any]] = {}
    results = []
    for p in properties_db:
        if c and p.city_id != c.id:
            continue
        if s and p.scheme_id != s.id:
            continue
        if use_type and p.use_type.lower() != use_type.lower():
            continue
        if category and p.category.lower() != category.lower():
            continue
        if min_price is not None and p.price < min_price:
            continue
        if max_price is not None and p.price > max_price:
            continue
        if bedrooms is not None and (p.bedrooms or 0) < bedrooms:
            continue
        if min_bathrooms is not None and (p.bathrooms or 0) < min_bathrooms:
            continue
        if min_marla is not None and (p.marla_area or 0) < min_marla:
            continue
        if max_marla is not None and (p.marla_area or 0) > max_marla:
            continue
        if featured is not None and p.featured != featured:
            continue
        if status and p.status.lower() != status.lower():
            continue
        if feature_q and feature_q not in " | ".join([*p.amenities, p.description or "", p.title]).lower():
            continue
        if near_cat:
            hit = _nearest_poi(p, near_cat, near_km)
            if hit is None:
                continue
            near_hits[p.id] = hit
        results.append(p)
    if near_cat:  # closest first
        results.sort(key=lambda p: near_hits[p.id]["distance_km"])
    place_info: Optional[Dict[str, Any]] = None
    place_dist: Dict[str, float] = {}
    outside: List[Property] = []
    if near_place:
        loc = geo.locate(near_place)
        if not loc:
            return dump({"count": 0, "returned": 0, "results": [], "near_place": {"query": near_place, "found": False},
                         "note": f"Couldn't find '{near_place}' on the map."})
        place_dist = {p.id: haversine_km(loc["lat"], loc["lon"], p.latitude, p.longitude)
                      for p in results if p.latitude is not None and p.longitude is not None}
        ranked = sorted((p for p in results if p.id in place_dist), key=lambda p: place_dist[p.id])
        results = [p for p in ranked if place_dist[p.id] <= near_km]
        outside = [p for p in ranked if place_dist[p.id] > near_km]
        place_info = {"query": near_place, "found": True, "name": loc["name"], "latitude": round(loc["lat"], 5),
                      "longitude": round(loc["lon"], 5), "radius_km": near_km}

    long_term_memory["search_history"].append(
        {
            "at": datetime.now().isoformat(),
            "query": {
                "city": city,
                "use_type": use_type,
                "category": category,
                "min_price": min_price,
                "max_price": max_price,
                "bedrooms": bedrooms,
            },
            "results": len(results),
        }
    )
    remember("search", {"city": city, "use_type": use_type, "count": len(results)})
    payload = []
    for p in results[: max(0, limit)]:
        d = model_dict(p)
        d["city_name"] = city_name(p.city_id)
        if p.id in near_hits:
            d["nearby"] = near_hits[p.id]
        if p.id in place_dist:
            d["distance_km"] = round(place_dist[p.id], 2)
        payload.append(d)
    out: Dict[str, Any] = {"count": len(results), "returned": len(payload), "results": payload}
    if place_info:
        out["near_place"] = place_info
        if not results and outside:
            rows = []
            for p in outside[:3]:
                d = model_dict(p)
                d["city_name"] = city_name(p.city_id)
                d["distance_km"] = round(place_dist[p.id], 2)
                rows.append(d)
            out["nearest_outside_radius"] = rows
    return dump(out)


# What people say -> POI category ("school ke paas", "masjid ke qareeb", "near the mall").
NEAR_CATEGORIES: Dict[str, str] = {
    "school": "education", "college": "education", "university": "education", "education": "education",
    "mosque": "worship", "masjid": "worship", "worship": "worship",
    "hospital": "health", "clinic": "health", "health": "health",
    "mall": "shopping", "market": "shopping", "shopping": "shopping", "shop": "shopping",
    "park": "park", "bank": "bank", "atm": "bank", "restaurant": "restaurant", "cafe": "restaurant",
    "transport": "transport", "metro": "transport", "bus": "transport", "station": "transport",
    "fuel": "fuel", "petrol": "fuel", "government": "government",
}
# Plain names for each POI category, used in answers and on the listing page.
NEAR_LABELS: Dict[str, str] = {
    "education": "School / college", "worship": "Mosque", "health": "Hospital / clinic",
    "shopping": "Mall / market", "park": "Park", "bank": "Bank", "restaurant": "Restaurant",
    "transport": "Public transport", "fuel": "Fuel station", "government": "Government office",
}


def _poi_hit(poi: "PointOfInterest", meters: float) -> Dict[str, Any]:
    return {
        "category": poi.category,
        "kind": NEAR_LABELS.get(poi.category, poi.category.title()),
        "name": poi.name,
        "distance_km": round(meters / 1000.0, 2),
        "walk_minutes": round(meters / 80.0),  # ~4.8 km/h
    }


def _nearest_poi(p: "Property", category: str, within_km: float) -> Optional[Dict[str, Any]]:
    """The closest place of ``category`` within ``within_km`` of a listing (the portal's
    POIs and the OpenStreetMap place data), or None."""
    if p.latitude is None or p.longitude is None:
        return None
    best: Optional[Tuple[float, "PointOfInterest"]] = None
    for poi in pois_db:
        if poi.category != category:
            continue
        d = gis.haversine_m(p.latitude, p.longitude, poi.latitude, poi.longitude)
        if d <= within_km * 1000.0 and (best is None or d < best[0]):
            best = (d, poi)
    mapped = geo.nearest_places(p.latitude, p.longitude, within_km, category=category, limit=1)
    if mapped and (best is None or mapped[0]["distance_km"] * 1000.0 < best[0]):
        return _map_hit(mapped[0])
    return _poi_hit(best[1], best[0]) if best else None


def _map_hit(row: Dict[str, Any]) -> Dict[str, Any]:
    """A geo.nearest_places row in the same shape as _poi_hit."""
    return {"category": row["category"], "kind": row["kind"], "name": row["name"],
            "distance_km": row["distance_km"], "walk_minutes": row["walk_minutes"]}


@mcp.tool()
def property_nearby(property_id: str, radius_km: float = 3.0) -> str:
    """Nearby places for a listing: the closest school, mosque, hospital, mall, park,
    transport, etc. within ``radius_km``, closest first (from the portal's POI data)."""
    p = find_property(property_id)
    if not p:
        return dump({"error": f"Property not found: {property_id}"})
    if p.latitude is None or p.longitude is None:
        return dump({"property_id": p.id, "radius_km": radius_km, "nearby": [], "note": "This listing has no map location."})
    best: Dict[str, Dict[str, Any]] = {}
    for poi in pois_db:
        d = gis.haversine_m(p.latitude, p.longitude, poi.latitude, poi.longitude)
        if d <= radius_km * 1000.0 and (poi.category not in best or d / 1000.0 < best[poi.category]["distance_km"]):
            best[poi.category] = _poi_hit(poi, d)
    mapped = geo.nearest_places(p.latitude, p.longitude, radius_km, limit=2000)
    counts: Dict[str, int] = {}
    for row in mapped:
        counts[row["kind"]] = counts.get(row["kind"], 0) + 1
        if row["category"] not in best or row["distance_km"] < best[row["category"]]["distance_km"]:
            best[row["category"]] = _map_hit(row)
    rows = sorted(best.values(), key=lambda r: r["distance_km"])
    return dump({"property_id": p.id, "radius_km": radius_km, "nearby": rows, "counts_within_radius": counts})


@mcp.tool()
def places_find(kind: Optional[str] = None, area: Optional[str] = None, near: Optional[str] = None,
                radius_km: float = 2.0, name: Optional[str] = None, limit: int = 15) -> str:
    """Find and count real places (schools, malls, hospitals, mosques, universities, parks …)
    inside an area ("Bahria Town Phase 8 Rawalpindi", "DHA Phase 2 Islamabad", "G-13") or
    within ``radius_km`` of a named place ("Rawalpindi Medical University")."""
    return dump(geo.find_places(kind=kind, name=name, area=area, near=near, radius_km=radius_km, limit=limit))


@mcp.tool()
def area_profile(area: str) -> str:
    """Population (estimate), size, density, development level, facilities, portal listings
    and nearby housing areas of a society, sector, phase or neighbourhood — plus the
    portal's own development details when it is a registered housing scheme."""
    result = geo.area_profile(area, properties_db)
    scheme = resolve_scheme(area)
    if not scheme:
        q = geo.tokens(area)
        scheme = next((s for s in housing_schemes_db if q and all(w in geo.tokens(s.name) for w in q)), None)
    if scheme:
        result["portal_scheme"] = {k: v for k, v in model_dict(scheme).items() if k in (
            "name", "developer", "established_year", "total_units", "development_status", "approval_authority",
            "possession_status", "utilities", "population", "description") and v not in (None, [], "")}
        result["portal_scheme"]["city"] = city_name(scheme.city_id)
    return dump(result)


@mcp.tool()
def map_view(listing_id: Optional[str] = None, place: Optional[str] = None, kinds: Optional[List[str]] = None,
             radius_km: float = 2.0, per_kind: int = 3) -> str:
    """A map of a listing (or a named place / area) with the nearest schools, mosques, parks,
    malls, hospitals … as markers — what the apps draw as a map card."""
    kinds = [k.strip().lower() for k in (kinds or geo.MAP_KINDS) if k and k.strip()]
    unknown = [k for k in kinds if k not in geo.KINDS]
    if unknown:
        return dump({"error": f"Unknown kinds {unknown}. Use: {', '.join(geo.KINDS)}"})
    focus: Dict[str, Any]
    if listing_id:
        p = find_property(listing_id)
        if not p:
            return dump({"error": f"Property not found: {listing_id}"})
        if p.latitude is None or p.longitude is None:
            return dump({"error": "This listing has no map location yet."})
        focus = {"type": "listing", "id": p.id, "name": p.title, "latitude": p.latitude, "longitude": p.longitude,
                 "price": p.price, "city": city_name(p.city_id)}
    elif place:
        loc = geo.locate(place)
        if not loc:
            return dump({"error": f"Couldn't find '{place}' on the map."})
        focus = {"type": "place", "name": loc["name"], "latitude": round(loc["lat"], 6), "longitude": round(loc["lon"], 6)}
    else:
        return dump({"error": "Give a listing_id or a place."})
    lat, lon = focus["latitude"], focus["longitude"]
    per_kind = max(1, min(per_kind, 10))
    markers = geo.map_markers(lat, lon, kinds, radius_km=radius_km, per_kind=per_kind)
    while len(markers) < 3 and radius_km < 6:  # outskirts: look a little further
        radius_km = min(6.0, radius_km * 2)
        markers = geo.map_markers(lat, lon, kinds, radius_km=radius_km, per_kind=per_kind)
    listings = []
    if focus["type"] == "place":  # listings around a place
        for p in properties_db:
            if p.latitude is not None and haversine_km(lat, lon, p.latitude, p.longitude) <= radius_km:
                listings.append({"id": p.id, "name": p.title, "latitude": p.latitude, "longitude": p.longitude,
                                 "price": p.price, "distance_km": round(haversine_km(lat, lon, p.latitude, p.longitude), 2)})
    return dump({"focus": focus, "radius_km": radius_km, "kinds": kinds, "markers": markers, "listings": listings,
                 "tiles": {"url": geo.TILE_URL, "attribution": geo.TILE_ATTRIBUTION},
                 "overlays": masterplan.overlays_at(lat, lon), "attribution": geo.ATTRIBUTION})


# ---------- DHA master plans ----------


def _plan_point(place: Optional[str] = None, listing_id: Optional[str] = None, plan: Optional[str] = None,
                latitude: Optional[float] = None, longitude: Optional[float] = None
                ) -> Optional[Tuple[float, float, str]]:
    """Resolve where to look: a listing, a label on the plan ("C10 commercial"), a place, or a point."""
    if latitude is not None and longitude is not None:
        return latitude, longitude, f"{latitude:.5f}, {longitude:.5f}"
    if listing_id:
        p = find_property(listing_id)
        if p and p.latitude is not None:
            return p.latitude, p.longitude, p.title
        return None
    if place:
        hit = masterplan.search(place, plan=plan, limit=1)
        if hit["results"] and (plan or hit["count"] <= 25):
            r = hit["results"][0]
            return r["latitude"], r["longitude"], f"{r['text']} ({r['plan']})"
        loc = geo.locate(place)
        if loc:
            return loc["lat"], loc["lon"], loc["name"]
    if plan:
        meta = masterplan.find_plan(plan)
        if meta:
            return meta["center"][0], meta["center"][1], meta["name"]
    return None


@mcp.tool()
def masterplan_list() -> str:
    """The DHA master plans loaded into the portal (outline, accuracy, map overlay, label counts)."""
    return dump({"count": len(masterplan.plans()), "plans": masterplan.plans(), "attribution": masterplan.ATTRIBUTION})


@mcp.tool()
def masterplan_summary(plan: str) -> str:
    """A DHA phase from its master plan: plot sizes, sectors / blocks, named roads, mosques, parks,
    schools, commercial areas, clubs, gates, the sheet's area statement, and web facts."""
    return dump(masterplan.summary(plan))


@mcp.tool()
def masterplan_search(query: str, plan: Optional[str] = None, category: Optional[str] = None, limit: int = 20) -> str:
    """Find text on the master plans ("C10 commercial", "Jinnah Blvd", "masjid", "plot 23 street 13")."""
    return dump(masterplan.search(query, plan=plan, category=category, limit=limit))


@mcp.tool()
def masterplan_at(place: Optional[str] = None, listing_id: Optional[str] = None, plan: Optional[str] = None,
                  latitude: Optional[float] = None, longitude: Optional[float] = None, radius_m: float = 200.0) -> str:
    """What the master plan shows around a listing, a place or a point (roads, plot sizes, parks, mosques …)."""
    pt = _plan_point(place, listing_id, plan, latitude, longitude)
    if not pt:
        return dump({"error": "Couldn't find that location."})
    return dump({"location": pt[2], "latitude": pt[0], "longitude": pt[1], **masterplan.at(pt[0], pt[1], radius_m)})


@mcp.tool()
def masterplan_view(plan: Optional[str] = None, place: Optional[str] = None, listing_id: Optional[str] = None,
                    radius_m: float = 250.0) -> str:
    """A section of a master plan to show: a readable close-up image (snapshot_url) and a map with
    the plan overlaid, centred on a listing, a label on the plan or a place."""
    pt = _plan_point(place, listing_id, plan)
    if not pt:
        return dump({"error": "Couldn't find that location."})
    lat, lon, label = pt
    meta = masterplan.find_plan(plan) if plan else None
    covering = masterplan.plans_at(lat, lon)
    if meta is None or (covering and meta not in covering):
        meta = covering[0] if covering else meta
    if not meta:
        return dump({"error": f"{label} is not on any loaded master plan.", "plans": [p["name"] for p in masterplan.plans()]})
    radius_m = max(80.0, min(radius_m, 3000.0))
    q = f"lat={lat:.6f}&lon={lon:.6f}&radius_m={radius_m:.0f}"
    view = json.loads(map_view(place=None, listing_id=listing_id, radius_km=1.0)) if listing_id else None
    if not view or "error" in view:
        view = {"focus": {"type": "place", "name": label, "latitude": lat, "longitude": lon}, "radius_km": 1.0, "kinds": [],
                "markers": [], "listings": [], "tiles": {"url": geo.TILE_URL, "attribution": geo.TILE_ATTRIBUTION},
                "overlays": masterplan.overlays_at(lat, lon), "attribution": geo.ATTRIBUTION}
    return dump({
        "plan": meta["name"], "plan_key": meta["key"], "location": label, "latitude": lat, "longitude": lon,
        "radius_m": radius_m, "snapshot_url": f"/masterplans/{meta['key']}/snapshot.png?{q}",
        "map": view, "on_the_plan": masterplan.at(lat, lon, min(radius_m, 400.0)),
        "accuracy": meta["accuracy"], "attribution": masterplan.ATTRIBUTION,
    })


@mcp.tool()
def geo_locate(query: str) -> str:
    """Where a named place or area is (centre point and the matched areas)."""
    loc = geo.locate(query)
    if not loc:
        return dump({"found": False, "query": query})
    return dump({"found": True, "query": query, "name": loc["name"], "kind": loc["kind"],
                 "latitude": round(loc["lat"], 5), "longitude": round(loc["lon"], 5),
                 "matched_areas": loc.get("areas"), "source": loc["source"]})


# ---------- GIS ----------


@mcp.tool()
def get_city_coordinates(city: str) -> str:
    """Get the coordinates of a city."""
    c = resolve_city(city)
    if not c:
        return dump({"error": f"City not found: {city}"})
    return dump({"city": c.name, "latitude": c.latitude, "longitude": c.longitude})


@mcp.tool()
def set_property_coordinates(property_id: str, latitude: float, longitude: float) -> str:
    """Set/update the GPS coordinates of a property."""
    p = find_property(property_id)
    if not p:
        return dump({"error": f"Property not found: {property_id}"})
    p.latitude, p.longitude = latitude, longitude
    p.updated_at = datetime.now()
    return dump({"property_id": property_id, "latitude": latitude, "longitude": longitude})


@mcp.tool()
def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> str:
    """Haversine distance between two coordinates, in km and miles."""
    km = haversine_km(lat1, lon1, lat2, lon2)
    return dump({"km": km, "miles": round(km * 0.621371, 3)})


@mcp.tool()
def get_property_distance(property_id_1: str, property_id_2: str) -> str:
    """Distance between two properties (both must have coordinates)."""
    a, b = find_property(property_id_1), find_property(property_id_2)
    if not a or not b:
        return dump({"error": "One or both properties not found"})
    if None in (a.latitude, a.longitude, b.latitude, b.longitude):
        return dump({"error": "Both properties need latitude and longitude"})
    km = haversine_km(a.latitude, a.longitude, b.latitude, b.longitude)
    return dump(
        {
            "from": {"id": a.id, "title": a.title},
            "to": {"id": b.id, "title": b.title},
            "km": km,
            "miles": round(km * 0.621371, 3),
        }
    )


@mcp.tool()
def search_nearby_properties(
    latitude: float,
    longitude: float,
    radius_km: float = 5.0,
    use_type: Optional[str] = None,
    category: Optional[str] = None,
    max_price: Optional[float] = None,
    limit: int = 20,
) -> str:
    """Find properties within `radius_km` of a point, sorted by distance."""
    hits = []
    for p in properties_db:
        if p.latitude is None or p.longitude is None:
            continue
        if use_type and p.use_type.lower() != use_type.lower():
            continue
        if category and p.category.lower() != category.lower():
            continue
        if max_price is not None and p.price > max_price:
            continue
        d = haversine_km(latitude, longitude, p.latitude, p.longitude)
        if d <= radius_km:
            hits.append((d, p))
    hits.sort(key=lambda x: x[0])
    results = []
    for d, p in hits[: max(0, limit)]:
        item = model_dict(p)
        item["distance_km"] = d
        item["city_name"] = city_name(p.city_id)
        results.append(item)
    remember("nearby", {"lat": latitude, "lon": longitude, "radius_km": radius_km, "count": len(results)})
    return dump({"origin": {"latitude": latitude, "longitude": longitude}, "radius_km": radius_km, "count": len(results), "results": results})


# ---------- Units ----------


@mcp.tool()
def convert_area(value: float, from_unit: str, to_unit: str) -> str:
    """Convert an area between sqft, sqm, sqyd, marla, kanal and acre."""
    result = convert_area_value(value, from_unit, to_unit)
    if result is None:
        return dump({"error": f"Unknown unit. Supported: {list(_AREA_UNITS)}"})
    return dump({"value": value, "from": from_unit, "to": to_unit, "result": result})


# ---------- GIS engine ----------


def _entity_center(entity_type: str, entity_id: str):
    """Resolve (lat, lon, name) for an entity, falling back sensibly."""
    if entity_type == "city":
        c = find_city(entity_id)
        if c:
            return c.latitude, c.longitude, c.name
    elif entity_type == "scheme":
        s = find_scheme(entity_id)
        if s:
            if s.latitude is not None:
                return s.latitude, s.longitude, s.name
            c = find_city(s.city_id)
            return (c.latitude if c else None), (c.longitude if c else None), s.name
    elif entity_type == "block":
        b = find_block(entity_id)
        if b:
            if b.latitude is not None:
                return b.latitude, b.longitude, b.name
            s = find_scheme(b.scheme_id)
            if s:
                if s.name:
                    pass
                c = find_city(s.city_id) if s else None
                return (c.latitude if c else None), (c.longitude if c else None), b.name
    elif entity_type == "bigproject":
        p = find_project(entity_id)
        if p:
            return p.latitude, p.longitude, p.name
    return None, None, "Unknown"


def _entity_properties(entity_type: str, entity_id: str) -> List[Property]:
    if entity_type == "city":
        return [p for p in properties_db if p.city_id == entity_id]
    if entity_type == "scheme":
        return [p for p in properties_db if p.scheme_id == entity_id]
    if entity_type == "block":
        return [p for p in properties_db if p.block_zone_area_id == entity_id]
    if entity_type == "bigproject":
        proj = find_project(entity_id)
        if proj:
            return [p for p in properties_db if p.city_id == proj.city_id]
    return []


@mcp.tool()
def gis_list_base_maps() -> str:
    """List available base maps (Google Earth-style imagery + open alternatives)."""
    return dump({"default": gis.DEFAULT_BASE_MAP, "count": len(gis.BASE_MAPS), "base_maps": gis.BASE_MAPS})


@mcp.tool()
def gis_get_base_map(base_map_id: str) -> str:
    """Get one base map definition (tile URL template, attribution, max zoom)."""
    b = gis.get_base_map(base_map_id)
    if not b:
        return dump({"error": f"Unknown base map: {base_map_id}", "available": [x["id"] for x in gis.BASE_MAPS]})
    return dump(b)


@mcp.tool()
def gis_add_layer(
    entity_type: str,
    entity_id: str,
    name: str,
    geojson: Dict[str, Any],
    layer_type: str = "master_plan",
    description: Optional[str] = None,
    base_map: Optional[str] = None,
    style: Optional[Dict[str, Any]] = None,
    z_index: int = 0,
    image_url: Optional[str] = None,
    source_url: Optional[str] = None,
) -> str:
    """Add a GeoJSON layer (master plan / boundary / zone / plot layout / road) to an entity."""
    layer = gis.GeoLayer(
        name=name,
        layer_type=layer_type,
        entity_type=entity_type,
        entity_id=entity_id,
        description=description,
        geojson=geojson,
        base_map=base_map or gis.DEFAULT_BASE_MAP,
        image_url=image_url,
        source_url=source_url,
        z_index=z_index,
        **({"style": style} if style else {}),
    )
    gis.add_layer(layer)
    return dump_model(layer)


@mcp.tool()
def gis_get_layer(layer_id: str) -> str:
    """Get a GIS layer by id (includes its full GeoJSON)."""
    l = gis.find_layer(layer_id)
    if not l:
        return dump({"error": f"Layer not found: {layer_id}"})
    return dump_model(l)


@mcp.tool()
def gis_list_layers(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    layer_type: Optional[str] = None,
) -> str:
    """List GIS layers, optionally filtered by entity and/or layer type."""
    layers = gis.list_layers(entity_type=entity_type, entity_id=entity_id, layer_type=layer_type)
    out = [
        {
            "id": l.id,
            "name": l.name,
            "layer_type": l.layer_type,
            "entity_type": l.entity_type,
            "entity_id": l.entity_id,
            "base_map": l.base_map,
            "visible": l.visible,
            "features": len(l.geojson.get("features", [])),
            "image_url": l.image_url,
        }
        for l in layers
    ]
    return dump({"count": len(out), "layers": out})


@mcp.tool()
def gis_update_layer(
    layer_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    base_map: Optional[str] = None,
    visible: Optional[bool] = None,
    opacity: Optional[float] = None,
    z_index: Optional[int] = None,
    style: Optional[Dict[str, Any]] = None,
    geojson: Optional[Dict[str, Any]] = None,
) -> str:
    """Update a GIS layer (visibility, style, base map, geometry, ...)."""
    l = gis.find_layer(layer_id)
    if not l:
        return dump({"error": f"Layer not found: {layer_id}"})
    for key, value in {
        "name": name,
        "description": description,
        "base_map": base_map,
        "visible": visible,
        "opacity": opacity,
        "z_index": z_index,
        "style": style,
        "geojson": geojson,
    }.items():
        if value is not None:
            setattr(l, key, value)
    l.updated_at = datetime.now()
    return dump_model(l)


@mcp.tool()
def gis_delete_layer(layer_id: str) -> str:
    """Delete a GIS layer."""
    ok = gis.delete_layer(layer_id)
    return dump({"deleted": ok, "layer_id": layer_id, "remaining": len(gis.GIS_LAYERS)})


@mcp.tool()
def gis_add_master_plan(
    entity_type: str,
    entity_id: str,
    name: str,
    north: float,
    south: float,
    east: float,
    west: float,
    image_url: Optional[str] = None,
    source_url: Optional[str] = None,
    base_map: Optional[str] = None,
    description: Optional[str] = None,
    layer_type: str = "master_plan",
    style: Optional[Dict[str, Any]] = None,
) -> str:
    """Register a housing-society/zone master plan as a rectified geo-layer.

    The plan is anchored to a geographic rectangle (north/south/east/west), so the
    raster (``image_url``) lines up with real coordinates on the base map.
    If the entity has no coordinates yet, they are set to the plan centroid.
    """
    if north <= south or east <= west:
        return dump({"error": "Require north > south and east > west"})
    footprint = gis.plan_footprint(north, south, east, west)
    feature = dict(footprint)
    feature["properties"] = {"name": name, "description": description or f"Master plan of {name}"}
    layer = gis.GeoLayer(
        name=name,
        layer_type=layer_type,
        entity_type=entity_type,
        entity_id=entity_id,
        description=description,
        geojson=gis.feature_collection([feature]),
        base_map=base_map or gis.DEFAULT_BASE_MAP,
        image_url=image_url,
        source_url=source_url,
        **({"style": style} if style else {}),
    )
    gis.add_layer(layer)

    # Anchor the entity if it has no coordinates yet.
    centroid = gis.polygon_centroid(feature["geometry"]["coordinates"][0])
    lat, lon, _ = _entity_center(entity_type, entity_id)
    anchored = False
    if lat is None and centroid:
        if entity_type == "scheme":
            s = find_scheme(entity_id)
            if s:
                s.latitude, s.longitude, anchored = centroid[0], centroid[1], True
        elif entity_type == "city":
            c = find_city(entity_id)
            if c:
                c.latitude, c.longitude, anchored = centroid[0], centroid[1], True
        elif entity_type == "block":
            b = find_block(entity_id)
            if b:
                b.latitude, b.longitude, anchored = centroid[0], centroid[1], True

    return dump(
        {
            "layer": model_dict(layer),
            "centroid": {"latitude": centroid[0], "longitude": centroid[1]},
            "entity_coordinates_anchored": anchored,
        }
    )


@mcp.tool()
def gis_list_master_plans(entity_type: Optional[str] = None, entity_id: Optional[str] = None) -> str:
    """List master-plan layers (and other registered plan layers)."""
    layers = [l for l in gis.list_layers(entity_type=entity_type, entity_id=entity_id) if l.layer_type in ("master_plan", "zone", "plot_layout")]
    out = [
        {
            "id": l.id,
            "name": l.name,
            "layer_type": l.layer_type,
            "entity_type": l.entity_type,
            "entity_id": l.entity_id,
            "image_url": l.image_url,
            "source_url": l.source_url,
            "base_map": l.base_map,
            "bbox": gis.geojson_bbox(l.geojson),
        }
        for l in layers
    ]
    return dump({"count": len(out), "master_plans": out})


@mcp.tool()
def gis_add_boundary(
    entity_type: str,
    entity_id: str,
    name: str,
    coordinates: List[List[float]],
    style: Optional[Dict[str, Any]] = None,
) -> str:
    """Add a boundary polygon layer. ``coordinates`` are [lat, lon] pairs (min 3)."""
    if len(coordinates) < 3:
        return dump({"error": "A boundary needs at least 3 [lat, lon] points"})
    feature = gis.polygon_feature(coordinates, {"name": name})
    layer = gis.GeoLayer(
        name=name,
        layer_type="boundary",
        entity_type=entity_type,
        entity_id=entity_id,
        geojson=gis.feature_collection([feature]),
        style=style or {"color": "#2b8cbe", "fillColor": "#2b8cbe", "fillOpacity": 0.15, "weight": 2, "opacity": 0.9},
    )
    gis.add_layer(layer)
    area = gis.polygon_area_sqm(feature["geometry"]["coordinates"][0])
    return dump(
        {
            "layer_id": layer.id,
            "name": name,
            "area_sqm": round(area, 2),
            "area_sqft": round(area * 10.7639, 2),
            "area_marla": sqft_to_marla(area * 10.7639),
            "area_kanal": round(area * 10.7639 / KANAL_TO_SQFT, 4),
        }
    )


@mcp.tool()
def gis_add_zone(
    entity_type: str,
    entity_id: str,
    name: str,
    coordinates: List[List[float]],
    zone_type: str = "residential",
    style: Optional[Dict[str, Any]] = None,
) -> str:
    """Add a zone polygon layer (residential / commercial / industrial / mixed)."""
    if len(coordinates) < 3:
        return dump({"error": "A zone needs at least 3 [lat, lon] points"})
    feature = gis.polygon_feature(coordinates, {"name": name, "zone_type": zone_type})
    palette = {"residential": "#2ca02c", "commercial": "#ff7f0e", "industrial": "#7f7f7f", "mixed": "#9467bd"}
    color = palette.get(zone_type.lower(), "#e6194b")
    layer = gis.GeoLayer(
        name=name,
        layer_type="zone",
        entity_type=entity_type,
        entity_id=entity_id,
        geojson=gis.feature_collection([feature]),
        style=style or {"color": color, "fillColor": color, "fillOpacity": 0.25, "weight": 2, "opacity": 0.9},
    )
    gis.add_layer(layer)
    return dump({"layer_id": layer.id, "name": name, "zone_type": zone_type})


@mcp.tool()
def gis_properties_in_bounds(south: float, west: float, north: float, east: float, limit: int = 50) -> str:
    """Find properties inside a lat/lon bounding box."""
    if north <= south or east <= west:
        return dump({"error": "Require north > south and east > west"})
    hits = []
    for p in properties_db:
        if p.latitude is None or p.longitude is None:
            continue
        if south <= p.latitude <= north and west <= p.longitude <= east:
            item = model_dict(p)
            item["city_name"] = city_name(p.city_id)
            hits.append(item)
    return dump({"count": len(hits), "bounds": {"south": south, "west": west, "north": north, "east": east}, "results": hits[:limit]})


@mcp.tool()
def gis_properties_in_polygon(coordinates: List[List[float]], limit: int = 50) -> str:
    """Find properties inside an arbitrary polygon. ``coordinates`` are [lat, lon] pairs."""
    if len(coordinates) < 3:
        return dump({"error": "A polygon needs at least 3 [lat, lon] points"})
    ring = gis.coords_from_latlon_list(coordinates)
    hits = []
    for p in properties_db:
        if p.latitude is None or p.longitude is None:
            continue
        if gis.point_in_polygon(p.latitude, p.longitude, ring):
            item = model_dict(p)
            item["city_name"] = city_name(p.city_id)
            hits.append(item)
    area = gis.polygon_area_sqm(ring)
    return dump({"count": len(hits), "polygon_area_sqm": round(area, 2), "results": hits[:limit]})


@mcp.tool()
def gis_point_in_layer(layer_id: str, latitude: float, longitude: float) -> str:
    """Test whether a point falls inside a layer's polygon."""
    l = gis.find_layer(layer_id)
    if not l:
        return dump({"error": f"Layer not found: {layer_id}"})
    result = False
    for feature in l.geojson.get("features", []):
        geom = feature.get("geometry", {})
        if geom.get("type") == "Polygon":
            rings = geom.get("coordinates", [])
            if rings and gis.point_in_polygon(latitude, longitude, rings[0]):
                result = True
                break
    return dump({"layer_id": layer_id, "latitude": latitude, "longitude": longitude, "inside": result})


@mcp.tool()
def gis_polygon_area(coordinates: List[List[float]]) -> str:
    """Geodesic area of a polygon ([lat, lon] pairs) in sqm, sqft, marla and kanal."""
    ring = gis.coords_from_latlon_list(coordinates)
    area = gis.polygon_area_sqm(ring)
    sqft = area * 10.7639
    return dump(
        {
            "area_sqm": round(area, 2),
            "area_sqft": round(sqft, 2),
            "area_marla": sqft_to_marla(sqft),
            "area_kanal": round(sqft / KANAL_TO_SQFT, 4),
            "area_acres": round(area / 4046.8564224, 4),
        }
    )


@mcp.tool()
def gis_polygon_centroid(coordinates: List[List[float]]) -> str:
    """Centroid of a polygon ([lat, lon] pairs)."""
    ring = gis.coords_from_latlon_list(coordinates)
    lat, lon = gis.polygon_centroid(ring)
    return dump({"latitude": round(lat, 7), "longitude": round(lon, 7)})


@mcp.tool()
def gis_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> str:
    """Compass bearing and distance from point 1 to point 2."""
    return dump(
        {
            "bearing_degrees": gis.bearing_deg(lat1, lon1, lat2, lon2),
            "distance_km": round(gis.haversine_m(lat1, lon1, lat2, lon2) / 1000, 3),
        }
    )


@mcp.tool()
def gis_destination(latitude: float, longitude: float, bearing: float, distance_m: float) -> str:
    """Project a point by a bearing and distance (metres)."""
    lat, lon = gis.destination_point(latitude, longitude, bearing, distance_m)
    return dump({"latitude": round(lat, 7), "longitude": round(lon, 7)})


@mcp.tool()
def gis_distance_matrix(origin_latitude: float, origin_longitude: float, property_ids: List[str]) -> str:
    """Straight-line distances from a point to several properties, sorted nearest first."""
    rows = []
    for pid in property_ids:
        p = find_property(pid)
        if not p or p.latitude is None or p.longitude is None:
            continue
        d = gis.haversine_m(origin_latitude, origin_longitude, p.latitude, p.longitude)
        rows.append({"property_id": pid, "title": p.title, "distance_km": round(d / 1000, 3)})
    rows.sort(key=lambda r: r["distance_km"])
    return dump({"origin": {"latitude": origin_latitude, "longitude": origin_longitude}, "count": len(rows), "distances": rows})


@mcp.tool()
def gis_export_geojson(entity_type: str, entity_id: str) -> str:
    """Export an entity's properties + GIS layers as one GeoJSON FeatureCollection."""
    features = []
    for p in _entity_properties(entity_type, entity_id):
        if p.latitude is not None and p.longitude is not None:
            features.append(gis.point_feature(p.latitude, p.longitude, {"kind": "property", "id": p.id, "name": p.title, "price": p.price, "category": p.category}))
    for l in gis.list_layers(entity_type=entity_type, entity_id=entity_id):
        for f in l.geojson.get("features", []):
            f.setdefault("properties", {})
            f["properties"]["kind"] = "layer"
            f["properties"]["layer_name"] = l.name
            f["properties"]["layer_type"] = l.layer_type
            features.append(f)
    return json.dumps(gis.feature_collection(features), indent=2)


def _entity_kml_layer(entity_type: str, entity_id: str) -> gis.GeoLayer:
    features = []
    for p in _entity_properties(entity_type, entity_id):
        if p.latitude is not None and p.longitude is not None:
            features.append(gis.point_feature(p.latitude, p.longitude, {"name": p.title, "description": f"{p.price:,.0f} {p.currency} · {p.category}"}))
    return gis.GeoLayer(
        name="Properties",
        layer_type="annotation",
        entity_type=entity_type,
        entity_id=entity_id,
        geojson=gis.feature_collection(features),
        style={"color": "#1f77b4", "fillColor": "#1f77b4", "fillOpacity": 0.9, "weight": 2, "opacity": 1.0},
    )


@mcp.tool()
def gis_export_kml(entity_type: str, entity_id: str) -> str:
    """Export an entity's layers + properties as KML (open in Google Earth)."""
    _, _, name = _entity_center(entity_type, entity_id)
    layers = list(gis.list_layers(entity_type=entity_type, entity_id=entity_id))
    prop_layer = _entity_kml_layer(entity_type, entity_id)
    if prop_layer.geojson["features"]:
        layers.append(prop_layer)
    return gis.build_kml(f"{name} — Real Estate Portal", layers)


@mcp.tool()
def gis_map_preview(
    entity_type: str,
    entity_id: str,
    base_map: Optional[str] = None,
    include_properties: bool = True,
    include_news: bool = False,
    include_poi: bool = False,
    lang: str = gis.DEFAULT_LANGUAGE,
    theme: str = gis.DEFAULT_THEME,
    lang_links: bool = True,
) -> str:
    """Return a self-contained HTML map (Leaflet) with base-map switcher + overlays.

    Set ``include_news=True`` to pin a scrolling real-estate news ticker to the top and
    ``include_poi=True`` to plot nearby points of interest.
    ``lang`` (``en`` / ``ur``, RTL supported) and ``theme`` (``auto`` / ``light`` /
    ``dark``) localise and re-skin the map chrome; set ``lang_links=False`` when the
    page is embedded (for example inside a report iframe).
    """
    lat, lon, name = _entity_center(entity_type, entity_id)
    layers = [l for l in gis.list_layers(entity_type=entity_type, entity_id=entity_id) if l.visible]
    overlays = [{"name": l.name, "geojson": l.geojson, "style": l.style} for l in layers]

    city_id = entity_id if entity_type == "city" else None
    scheme_id = entity_id if entity_type == "scheme" else None
    if entity_type == "scheme":
        s = find_scheme(entity_id)
        city_id = s.city_id if s else None
    elif entity_type == "block":
        b = find_block(entity_id)
        if b:
            s = find_scheme(b.scheme_id)
            city_id = s.city_id if s else None

    markers = []
    if include_properties:
        for p in _entity_properties(entity_type, entity_id):
            if p.latitude is not None and p.longitude is not None:
                markers.append({"lat": p.latitude, "lon": p.longitude, "title": p.title, "description": f"{p.price:,.0f} {p.currency}"})
    if include_poi:
        for poi in _poi_filter(city_id=city_id, scheme_id=scheme_id):
            markers.append({"lat": poi.latitude, "lon": poi.longitude,
                            "title": f"POI: {poi.name}", "description": poi.category})

    # centre: entity coords, else first overlay/marker
    if lat is None or lon is None:
        if markers:
            lat, lon = markers[0]["lat"], markers[0]["lon"]
        elif overlays:
            box = gis.geojson_bbox(overlays[0]["geojson"])
            if box:
                lat, lon = (box["south"] + box["north"]) / 2, (box["west"] + box["east"]) / 2
    if lat is None or lon is None:
        lat, lon = 30.3753, 69.3451  # Pakistan centre

    ticker = ""
    if include_news:
        items = _news_filter(city_id=city_id, scheme_id=scheme_id)[:25]
        ticker = gis.build_ticker_html([model_dict(n) for n in items], label="Real Estate News", lang=lang)

    return gis.build_map_html(
        title=name,
        center_lat=lat,
        center_lon=lon,
        zoom=14,
        base_map_id=base_map or gis.DEFAULT_BASE_MAP,
        overlays=overlays,
        markers=markers,
        ticker_html=ticker,
        lang=lang,
        theme=theme,
        lang_links=lang_links,
    )


@mcp.tool()
def gis_point_map(
    latitude: float,
    longitude: float,
    radius_km: float = 2.0,
    zoom: int = 14,
    base_map: Optional[str] = None,
    include_properties: bool = True,
    include_poi: bool = False,
    title: str = "Real Estate Portal",
    lang: str = gis.DEFAULT_LANGUAGE,
    theme: str = gis.DEFAULT_THEME,
    lang_links: bool = True,
) -> str:
    """Interactive Leaflet map centred on a point, optionally plotting nearby properties and POIs."""
    markers: List[Dict[str, Any]] = []
    radius_m = radius_km * 1000.0
    if include_properties:
        for p in properties_db:
            if p.latitude is None or p.longitude is None:
                continue
            if gis.haversine_m(latitude, longitude, p.latitude, p.longitude) <= radius_m:
                markers.append({"lat": p.latitude, "lon": p.longitude, "title": p.title,
                                "description": f"{p.price:,.0f} {p.currency}"})
    if include_poi:
        for poi in _poi_near(latitude, longitude, radius_m):
            markers.append({"lat": poi["latitude"], "lon": poi["longitude"],
                            "title": f"POI: {poi['name']}", "description": poi["category"]})
    return gis.build_map_html(
        title=title,
        center_lat=latitude,
        center_lon=longitude,
        zoom=zoom,
        base_map_id=base_map or gis.DEFAULT_BASE_MAP,
        markers=markers,
        lang=lang,
        theme=theme,
        lang_links=lang_links,
    )


@mcp.tool()
def portal_languages() -> str:
    """List the UI languages available for maps, reports and the ticker (code, name, text direction)."""
    return dump({"count": len(gis.SUPPORTED_LANGUAGES), "default": gis.DEFAULT_LANGUAGE,
                 "languages": gis.SUPPORTED_LANGUAGES})


@mcp.tool()
def portal_themes() -> str:
    """List the UI themes (``auto`` / ``light`` / ``dark``) and the CSS custom properties each one sets."""
    return dump({"count": len(gis.SUPPORTED_THEMES), "default": gis.DEFAULT_THEME,
                 "themes": gis.SUPPORTED_THEMES, "tokens": gis.THEME_TOKENS})


@mcp.tool()
def portal_strings(lang: str = "en") -> str:
    """Return the localisation dictionary for a language (English source string -> translation)."""
    code = gis.get_language(lang)["code"]
    table = gis.TRANSLATIONS.get(code, {})
    return dump({"language": code, "count": len(table), "strings": table,
                 "fallback_language": gis.DEFAULT_LANGUAGE})


@mcp.resource("gis://languages", name="UI languages", description="Supported UI languages and text direction.")
def res_gis_languages() -> str:
    return portal_languages()


@mcp.resource("gis://themes", name="UI themes", description="Supported UI themes and their CSS tokens.")
def res_gis_themes() -> str:
    return portal_themes()


@mcp.resource("gis://strings/{lang}", name="UI strings", description="Localisation dictionary for a language.")
def res_gis_strings(lang: str) -> str:
    return portal_strings(lang)


# ---------- GIS analysis: buffers, features, cost, population, economics ----------

# Editable planning assumptions (PKR unless noted). Override per-request where tools allow.
GIS_ASSUMPTIONS: Dict[str, Any] = {
    "avg_household_size": 5.6,
    "persons_per_bedroom": 1.6,
    "default_dwelling_persons": 4.5,
    "occupancy_rate": 0.85,
    "construction_cost_per_sqft": {
        "house": 4500.0,
        "building": 5000.0,
        "apartment": 6000.0,
        "office": 7000.0,
        "shop": 6500.0,
        "floor": 5500.0,
        "space": 4000.0,
        "warehouse": 3500.0,
        "shed": 2500.0,
        "plot": 0.0,
    },
    "infrastructure_cost_per_sqft": 350.0,  # roads, water, sewer, power
    "land_development_cost_per_sqft": 250.0,  # grading / levelling of plots
    "jobs_per_million_pkr_construction": 12.0,
    "operational_jobs_per_1000_sqm": 1.8,
    "economic_multiplier": 1.8,
    "annual_property_tax_rate": 0.005,
    "annual_rental_yield": 0.04,
    "commercial_activity_factor": 3.0,
}

_BUILT_CATEGORIES = {"house", "building", "apartment", "office", "shop", "floor", "space", "warehouse", "shed"}
_RESIDENTIAL_CATEGORIES = {"house", "apartment", "building", "floor", "plot", "space"}

METRIC_LABELS: Dict[str, Dict[str, str]] = {
    "property_count": {"label": "Properties", "unit": ""},
    "market_value": {"label": "Market value", "unit": "PKR"},
    "avg_price": {"label": "Average price", "unit": "PKR"},
    "price_per_marla": {"label": "Price / marla", "unit": "PKR"},
    "land_area_marla": {"label": "Land area", "unit": "marla"},
    "built_area_sqft": {"label": "Built area", "unit": "sqft"},
    "population": {"label": "Population", "unit": "persons"},
    "density_per_sqkm": {"label": "Density", "unit": "/km²"},
    "development_cost": {"label": "Development cost", "unit": "PKR"},
    "construction_cost": {"label": "Construction cost", "unit": "PKR"},
    "economic_output": {"label": "Economic output", "unit": "PKR"},
    "jobs": {"label": "Jobs", "unit": "jobs"},
    "annual_property_tax": {"label": "Annual property tax", "unit": "PKR"},
    "annual_rental_value": {"label": "Annual rental value", "unit": "PKR"},
}


def _property_area_sqft(p: Property) -> float:
    if p.total_area:
        return float(p.total_area)
    if p.marla_area:
        return float(marla_to_sqft(p.marla_area))
    if p.kanal_area:
        return float(kanal_to_sqft(p.kanal_area))
    if p.plot_area:
        return float(p.plot_area)
    return 0.0


def _property_metrics(props: List[Property]) -> Dict[str, Any]:
    by_category: Dict[str, int] = {}
    by_use_type: Dict[str, int] = {}
    built_by_category: Dict[str, float] = {}
    land_sqft = built_sqft = value = 0.0
    commercial_built_sqft = commercial_value = 0.0
    commercial_count = 0
    prices: List[float] = []

    for p in props:
        area = _property_area_sqft(p)
        cat = p.category or "unknown"
        by_category[cat] = by_category.get(cat, 0) + 1
        by_use_type[p.use_type] = by_use_type.get(p.use_type, 0) + 1
        value += p.price or 0.0
        prices.append(p.price or 0.0)
        if cat in _BUILT_CATEGORIES:
            built_sqft += area
            built_by_category[cat] = built_by_category.get(cat, 0.0) + area
            land_sqft += float(p.plot_area or 0.0)
            if p.use_type == "commercial":
                commercial_built_sqft += area
                commercial_value += p.price or 0.0
                commercial_count += 1
        else:
            land_sqft += area

    n = len(props)
    sqft = land_sqft + built_sqft
    # For areas with only built stock, value the product against total floor area.
    marla_base = sqft_to_marla(land_sqft if land_sqft else sqft)
    price_per_marla = (value / marla_base) if marla_base else 0.0
    plot_value = sum((p.price or 0.0) for p in props if p.category == "plot")
    return {
        "count": n,
        "by_category": by_category,
        "by_use_type": by_use_type,
        "land_sqft": round(land_sqft, 2),
        "built_sqft": round(built_sqft, 2),
        "marla_base": round(marla_base, 3),
        "built_by_category": {k: round(v, 2) for k, v in built_by_category.items()},
        "commercial_built_sqft": round(commercial_built_sqft, 2),
        "commercial_count": commercial_count,
        "commercial_value": round(commercial_value, 2),
        "total_market_value": round(value, 2),
        "plot_value": round(plot_value, 2),
        "avg_price": round(value / n, 2) if n else 0.0,
        "median_price": round(statistics.median(prices), 2) if prices else 0.0,
        "min_price": round(min(prices), 2) if prices else 0.0,
        "max_price": round(max(prices), 2) if prices else 0.0,
        "price_per_sqft": round(value / sqft, 2) if sqft else 0.0,
        "price_per_marla": round(price_per_marla, 2),
    }


def _dwelling_persons(p: Property, a: Dict[str, Any]) -> float:
    if p.bedrooms:
        return max(1.0, p.bedrooms * a["persons_per_bedroom"])
    return float(a["default_dwelling_persons"])


def _population_estimate(props: List[Property], total_units: Optional[int] = None) -> Dict[str, Any]:
    a = GIS_ASSUMPTIONS
    dwellings = 0
    persons = 0.0
    for p in props:
        if p.use_type == "residential" and p.category in _RESIDENTIAL_CATEGORIES:
            dwellings += 1
            persons += _dwelling_persons(p, a)
    pop = persons * a["occupancy_rate"]
    projected = None
    if total_units:
        projected = {
            "dwelling_units": total_units,
            "population": round(total_units * a["avg_household_size"] * a["occupancy_rate"]),
            "based_on": "total_units",
        }
    return {
        "dwellings_listed": dwellings,
        "population_from_listings": round(pop),
        "avg_household_size": a["avg_household_size"],
        "occupancy_rate": a["occupancy_rate"],
        "projected": projected,
    }


def _development_cost(land_sqft: float, built_by_category: Dict[str, float]) -> Dict[str, Any]:
    a = GIS_ASSUMPTIONS
    rates = a["construction_cost_per_sqft"]
    site_sqft = land_sqft or sum(built_by_category.values())
    land_dev = site_sqft * a["land_development_cost_per_sqft"]
    infra = site_sqft * a["infrastructure_cost_per_sqft"]
    construction = 0.0
    by_cat: Dict[str, float] = {}
    for cat, area in built_by_category.items():
        c = area * rates.get(cat, rates.get("building", 0.0))
        by_cat[cat] = round(c, 2)
        construction += c
    total = land_dev + infra + construction
    return {
        "land_sqft": round(site_sqft, 2),
        "land_development": round(land_dev, 2),
        "infrastructure": round(infra, 2),
        "construction": round(construction, 2),
        "construction_by_category": by_cat,
        "total": round(total, 2),
        "cost_per_sqft_of_land": round(total / site_sqft, 2) if site_sqft else 0.0,
    }


def _economic_impact(metrics: Dict[str, Any], cost: Dict[str, Any]) -> Dict[str, Any]:
    a = GIS_ASSUMPTIONS
    direct = cost["total"]
    total_output = direct * a["economic_multiplier"]
    construction_jobs = direct / 1_000_000 * a["jobs_per_million_pkr_construction"]
    operational_jobs = (
        metrics["commercial_built_sqft"] * 0.092903 / 1000 * a["operational_jobs_per_1000_sqm"]
    )
    market_value = metrics["total_market_value"]
    return {
        "direct_investment": round(direct, 2),
        "indirect_induced_output": round(total_output - direct, 2),
        "total_economic_output": round(total_output, 2),
        "economic_multiplier": a["economic_multiplier"],
        "construction_jobs": round(construction_jobs),
        "operational_jobs": round(operational_jobs),
        "jobs_total": round(construction_jobs + operational_jobs),
        "market_value": round(market_value, 2),
        "annual_property_tax": round(market_value * a["annual_property_tax_rate"], 2),
        "annual_rental_value": round(market_value * a["annual_rental_yield"], 2),
        "commercial_activity_value": round(metrics["commercial_value"] * a["commercial_activity_factor"], 2),
    }


def _area_analysis(
    name: str,
    props: List[Property],
    geometry: Optional[Dict[str, Any]] = None,
    area_sqm: Optional[float] = None,
    total_units: Optional[int] = None,
) -> Dict[str, Any]:
    metrics = _property_metrics(props)
    if area_sqm is None and geometry:
        area_sqm = _geometry_area_sqm(geometry)
    if area_sqm is None:
        geo_props = [p for p in props if p.latitude is not None and p.longitude is not None]
        if len(geo_props) >= 3:
            ring = gis.convex_hull([(p.longitude, p.latitude) for p in geo_props])
            ring.append(ring[0])
            area_sqm = gis.polygon_area_sqm(ring)
        else:
            area_sqm = metrics["land_sqft"] * 0.092903

    population = _population_estimate(props, total_units)
    cost = _development_cost(metrics["land_sqft"], metrics["built_by_category"])
    econ = _economic_impact(metrics, cost)

    density = 0.0
    if area_sqm:
        dense_km2 = area_sqm / 1_000_000
        density = round(population["population_from_listings"] / dense_km2, 1) if dense_km2 else 0.0
    population["density_per_sqkm"] = density

    sqft = area_sqm * 10.7639
    return {
        "name": name,
        "geometry": geometry,
        "area": {
            "area_sqm": round(area_sqm, 2),
            "area_sqft": round(sqft, 2),
            "area_marla": sqft_to_marla(sqft),
            "area_kanal": round(sqft / KANAL_TO_SQFT, 4),
            "area_acres": round(sqft / 43560.0, 4),
        },
        "properties": metrics,
        "population": population,
        "development_cost": cost,
        "economic_impact": econ,
        "assumptions": GIS_ASSUMPTIONS,
    }


def _geometry_area_sqm(geometry: Dict[str, Any]) -> Optional[float]:
    gtype = geometry.get("type")
    coords = geometry.get("coordinates") or []
    if gtype == "Polygon" and coords:
        outer = gis.polygon_area_sqm(coords[0])
        holes = sum(gis.polygon_area_sqm(r) for r in coords[1:])
        return max(0.0, outer - holes)
    if gtype == "MultiPolygon":
        return sum(
            _geometry_area_sqm({"type": "Polygon", "coordinates": poly}) or 0.0 for poly in coords
        )
    return None


def _entity_geometry(
    entity_type: str, entity_id: str, props: List[Property]
) -> Optional[Dict[str, Any]]:
    """Prefer a registered polygon layer, else a hull/bbox of the entity's properties."""
    for layer in gis.list_layers(entity_type=entity_type, entity_id=entity_id):
        for feature in layer.geojson.get("features", []):
            geom = feature.get("geometry", {})
            if geom.get("type") in ("Polygon", "MultiPolygon"):
                return geom
    pts = [(p.longitude, p.latitude) for p in props if p.latitude is not None and p.longitude is not None]
    if len(pts) >= 3:
        hull = gis.convex_hull(pts)
        if len(hull) >= 3:
            ring = [[lon, lat] for lon, lat in hull]
            ring.append(ring[0])
            return {"type": "Polygon", "coordinates": [ring]}
    if pts:
        box = gis.bbox_of_coords(pts)
        pad_lat = max(0.001, (box["north"] - box["south"]) * 0.1)
        pad_lon = max(0.001, (box["east"] - box["west"]) * 0.1)
        return {
            "type": "Polygon",
            "coordinates": [[
                [box["west"] - pad_lon, box["south"] - pad_lat],
                [box["east"] + pad_lon, box["south"] - pad_lat],
                [box["east"] + pad_lon, box["north"] + pad_lat],
                [box["west"] - pad_lon, box["north"] + pad_lat],
                [box["west"] - pad_lon, box["south"] - pad_lat],
            ]],
        }
    return None


def _scope_areas(scope_type: str, scope_id: str):
    """Return ([area dicts], scope_info) for a city/scheme/block."""
    scope_type = (scope_type or "").lower()
    if scope_type == "city":
        city = find_city(scope_id)
        if not city:
            return None, None
        areas = []
        for s in [s for s in housing_schemes_db if s.city_id == city.id]:
            props = [p for p in properties_db if p.scheme_id == s.id]
            areas.append(
                {
                    "name": s.name,
                    "entity_type": "scheme",
                    "entity_id": s.id,
                    "geometry": _entity_geometry("scheme", s.id, props),
                    "properties": props,
                    "total_units": s.total_units,
                }
            )
        info = {"name": city.name, "entity_type": "city", "entity_id": city.id}
        return areas, info
    if scope_type == "scheme":
        s = find_scheme(scope_id)
        if not s:
            return None, None
        areas = []
        for b in [b for b in block_zone_areas_db if b.scheme_id == s.id]:
            props = [p for p in properties_db if p.block_zone_area_id == b.id]
            areas.append(
                {
                    "name": b.name,
                    "entity_type": "block",
                    "entity_id": b.id,
                    "geometry": _entity_geometry("block", b.id, props),
                    "properties": props,
                    "total_units": None,
                }
            )
        info = {"name": s.name, "entity_type": "scheme", "entity_id": s.id}
        return areas, info
    if scope_type == "block":
        b = find_block(scope_id)
        if not b:
            return None, None
        props = [p for p in properties_db if p.block_zone_area_id == b.id]
        areas = [
            {
                "name": p.title,
                "entity_type": "property",
                "entity_id": p.id,
                "geometry": {"type": "Point", "coordinates": [p.longitude, p.latitude]}
                if p.latitude is not None and p.longitude is not None
                else None,
                "properties": [p],
                "total_units": None,
            }
            for p in props
        ]
        info = {"name": b.name, "entity_type": "block", "entity_id": b.id}
        return areas, info
    return None, None


def _metric_value(analysis: Dict[str, Any], metric: str) -> Optional[float]:
    m = analysis["properties"]
    return {
        "property_count": m["count"],
        "market_value": m["total_market_value"],
        "avg_price": m["avg_price"],
        "price_per_marla": m["price_per_marla"],
        "land_area_marla": analysis["area"]["area_marla"],
        "built_area_sqft": m["built_sqft"],
        "population": analysis["population"]["population_from_listings"],
        "density_per_sqkm": analysis["population"]["density_per_sqkm"],
        "development_cost": analysis["development_cost"]["total"],
        "construction_cost": analysis["development_cost"]["construction"],
        "economic_output": analysis["economic_impact"]["total_economic_output"],
        "jobs": analysis["economic_impact"]["jobs_total"],
        "annual_property_tax": analysis["economic_impact"]["annual_property_tax"],
        "annual_rental_value": analysis["economic_impact"]["annual_rental_value"],
    }.get(metric)


def _report_sections(analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
    area = analysis["area"]
    m = analysis["properties"]
    pop = analysis["population"]
    cost = analysis["development_cost"]
    econ = analysis["economic_impact"]

    def money(v: float) -> str:
        return f"{v:,.0f}"

    return [
        {
            "heading": "Key figures",
            "kind": "cards",
            "items": [
                ["Area", f"{area['area_acres']:,.2f}", "acres"],
                ["Properties", f"{m['count']:,}", f"{m['built_sqft']:,.0f} sqft built"],
                ["Market value", money(m["total_market_value"]), "PKR"],
                ["Population", f"{pop['population_from_listings']:,}", f"{pop['density_per_sqkm']:,}/km²"],
                ["Development cost", money(cost["total"]), "PKR"],
                ["Economic output", money(econ["total_economic_output"]), "PKR"],
                ["Jobs", f"{econ['jobs_total']:,}", "direct + operational"],
                ["Annual property tax", money(econ["annual_property_tax"]), "PKR"],
            ],
        },
        {
            "heading": "Area",
            "kind": "kv",
            "items": [
                ("Square feet", f"{area['area_sqft']:,.0f}"),
                ("Square metres", f"{area['area_sqm']:,.0f}"),
                ("Marla", f"{area['area_marla']:,.2f}"),
                ("Kanal", f"{area['area_kanal']:,.3f}"),
                ("Acres", f"{area['area_acres']:,.3f}"),
            ],
        },
        {
            "heading": "Properties",
            "kind": "table",
            "columns": ["Category", "Count", "Built sqft"],
            "numeric": ["Count", "Built sqft"],
            "rows": [
                [cat, str(cnt), f"{m['built_by_category'].get(cat, 0):,.0f}"]
                for cat, cnt in sorted(m["by_category"].items())
            ],
        },
        {
            "heading": "Valuation",
            "kind": "kv",
            "items": [
                ("Total market value (PKR)", money(m["total_market_value"])),
                ("Average price (PKR)", money(m["avg_price"])),
                ("Median price (PKR)", money(m["median_price"])),
                ("Price / sqft (PKR)", money(m["price_per_sqft"])),
                ("Price / marla (PKR)", money(m["price_per_marla"])),
            ],
        },
        {
            "heading": "Population",
            "kind": "kv",
            "items": [
                ("Dwellings listed", f"{pop['dwellings_listed']:,}"),
                ("Population (from listings)", f"{pop['population_from_listings']:,}"),
                ("Avg household size", f"{pop['avg_household_size']}"),
                ("Occupancy rate", f"{pop['occupancy_rate']:.0%}"),
                ("Density (/km²)", f"{pop['density_per_sqkm']:,}"),
            ]
            + (
                [("Projected population (total units)", f"{pop['projected']['population']:,}")]
                if pop.get("projected")
                else []
            ),
        },
        {
            "heading": "Development cost",
            "kind": "table",
            "columns": ["Component", "Amount (PKR)"],
            "numeric": ["Amount (PKR)"],
            "rows": [
                ["Land development", money(cost["land_development"])],
                ["Infrastructure (roads, water, sewer, power)", money(cost["infrastructure"])],
                ["Construction", money(cost["construction"])],
                ["Total", money(cost["total"])],
            ],
        },
        {
            "heading": "Economic impact",
            "kind": "kv",
            "items": [
                ("Direct investment (PKR)", money(econ["direct_investment"])),
                ("Indirect + induced (PKR)", money(econ["indirect_induced_output"])),
                ("Total economic output (PKR)", money(econ["total_economic_output"])),
                ("Economic multiplier", f"{econ['economic_multiplier']}x"),
                ("Construction jobs", f"{econ['construction_jobs']:,}"),
                ("Operational jobs", f"{econ['operational_jobs']:,}"),
                ("Annual rental value (PKR)", money(econ["annual_rental_value"])),
                ("Commercial activity value (PKR)", money(econ["commercial_activity_value"])),
            ],
        },
    ]


def _geo_center_of(geometry: Optional[Dict[str, Any]]):
    if not geometry:
        return None, None
    if geometry.get("type") == "Point":
        lon, lat = geometry["coordinates"]
        return lat, lon
    box = gis.geojson_bbox(geometry)
    if box:
        return (box["south"] + box["north"]) / 2, (box["west"] + box["east"]) / 2
    return None, None


@mcp.tool()
def gis_analysis_assumptions() -> str:
    """Show the planning assumptions used for cost / population / economic estimates."""
    return dump(GIS_ASSUMPTIONS)


@mcp.tool()
def gis_buffer_geometry(geometry: Dict[str, Any], distance_m: float, segments: int = 48) -> str:
    """Buffer any GeoJSON geometry (Point/Line/Polygon) by ``distance_m`` metres."""
    buffered = gis.buffer_geometry(geometry, distance_m, segments=segments)
    if not buffered:
        return dump({"error": "Could not buffer geometry (need a valid geometry and distance_m > 0)"})
    area_sqm = gis.polygon_area_sqm(buffered["coordinates"][0])
    return dump(
        {
            "geometry": buffered,
            "distance_m": distance_m,
            "area_sqm": round(area_sqm, 2),
            "area_hectares": round(area_sqm / 10_000, 4),
            "method": "vertex-circle convex hull (exact for points/lines/convex polygons)",
        }
    )


@mcp.tool()
def gis_buffer_point(latitude: float, longitude: float, radius_m: float, segments: int = 72) -> str:
    """Create a circular buffer polygon around a point."""
    geom = gis.circle_polygon(latitude, longitude, radius_m, segments)
    return dump(
        {
            "geometry": geom,
            "center": {"latitude": latitude, "longitude": longitude},
            "radius_m": radius_m,
            "area_sqm": round(gis.polygon_area_sqm(geom["coordinates"][0]), 2),
        }
    )


@mcp.tool()
def gis_add_buffer_layer(
    entity_type: str,
    entity_id: str,
    name: str,
    distance_m: float,
    source_layer_id: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    coordinates: Optional[List[List[float]]] = None,
    style: Optional[Dict[str, Any]] = None,
    layer_type: str = "buffer",
) -> str:
    """Add a buffer analysis layer: buffer an existing layer, a point, or a polygon."""
    geometry: Optional[Dict[str, Any]] = None
    if source_layer_id:
        src = gis.find_layer(source_layer_id)
        if not src:
            return dump({"error": f"Source layer not found: {source_layer_id}"})
        features = src.geojson.get("features", [])
        if not features:
            return dump({"error": "Source layer has no features"})
        geometry = features[0].get("geometry")
    elif latitude is not None and longitude is not None:
        geometry = {"type": "Point", "coordinates": [longitude, latitude]}
    elif coordinates:
        geometry = gis.polygon_feature(coordinates)["geometry"]
    if geometry is None:
        return dump({"error": "Provide source_layer_id, latitude/longitude, or coordinates"})

    buffered = gis.buffer_geometry(geometry, distance_m)
    if not buffered:
        return dump({"error": "Buffer failed"})
    feature = {"type": "Feature", "geometry": buffered, "properties": {"name": name, "distance_m": distance_m}}
    layer = gis.GeoLayer(
        name=name,
        layer_type=layer_type,
        entity_type=entity_type,
        entity_id=entity_id,
        description=f"{distance_m:,.0f} m buffer",
        geojson=gis.feature_collection([feature]),
        style=style
        or {"color": "#6f42c1", "fillColor": "#6f42c1", "fillOpacity": 0.18, "weight": 2, "opacity": 0.9},
    )
    gis.add_layer(layer)
    area_sqm = gis.polygon_area_sqm(buffered["coordinates"][0])
    return dump(
        {
            "layer_id": layer.id,
            "name": name,
            "distance_m": distance_m,
            "area_sqm": round(area_sqm, 2),
            "area_marla": sqft_to_marla(area_sqm * 10.7639),
        }
    )


@mcp.tool()
def gis_ring_analysis(latitude: float, longitude: float, radii_km: List[float], use_type: Optional[str] = None) -> str:
    """Concentric-ring (annulus) accessibility analysis around a point.

    For each ring returns the annulus geometry plus property / value / population stats.
    """
    radii_m = sorted(r * 1000.0 for r in radii_km if r > 0)
    if not radii_m:
        return dump({"error": "Provide at least one positive radius in km"})
    rings = gis.multi_ring_buffer(latitude, longitude, radii_m)

    candidates = properties_db
    if use_type:
        candidates = [p for p in candidates if p.use_type == use_type]

    out = []
    for ring in rings:
        inside = []
        for p in candidates:
            if p.latitude is None or p.longitude is None:
                continue
            d = gis.haversine_m(latitude, longitude, p.latitude, p.longitude)
            if ring["inner_m"] < d <= ring["outer_m"]:
                inside.append(p)
        area_sqm = math.pi * (ring["outer_m"] ** 2 - ring["inner_m"] ** 2)
        analysis = _area_analysis(
            f"{ring['inner_m']/1000:g}–{ring['outer_m']/1000:g} km",
            inside,
            geometry=ring["geometry"],
            area_sqm=area_sqm,
        )
        out.append(
            {
                "inner_km": ring["inner_m"] / 1000,
                "outer_km": ring["outer_m"] / 1000,
                "geometry": ring["geometry"],
                "summary": {
                    "properties": analysis["properties"]["count"],
                    "market_value": analysis["properties"]["total_market_value"],
                    "population": analysis["population"]["population_from_listings"],
                    "area_sqkm": analysis["area"]["area_sqm"] / 1_000_000,
                },
            }
        )
    return dump({"center": {"latitude": latitude, "longitude": longitude}, "rings": out})


@mcp.tool()
def gis_polygon_analysis(
    coordinates: List[List[float]],
    name: str = "Custom area",
    total_units: Optional[int] = None,
) -> str:
    """Full analysis of an arbitrary polygon: area, properties, population, cost, economics."""
    if len(coordinates) < 3:
        return dump({"error": "A polygon needs at least 3 [lat, lon] points"})
    ring = gis.coords_from_latlon_list(coordinates)
    geometry = {"type": "Polygon", "coordinates": [ring]}
    props = [
        p
        for p in properties_db
        if p.latitude is not None
        and p.longitude is not None
        and gis.point_in_polygon(p.latitude, p.longitude, ring)
    ]
    return dump(_area_analysis(name, props, geometry=geometry, total_units=total_units))


@mcp.tool()
def gis_area_analysis(entity_type: str, entity_id: str) -> str:
    """Full analysis of a city / scheme / block: area, properties, population, cost, economics."""
    props = _entity_properties(entity_type, entity_id)
    _, _, name = _entity_center(entity_type, entity_id)
    geometry = _entity_geometry(entity_type, entity_id, props)
    total_units = None
    if entity_type == "scheme":
        s = find_scheme(entity_id)
        total_units = s.total_units if s else None
    elif entity_type == "city":
        total_units = sum(
            (s.total_units or 0) for s in housing_schemes_db if s.city_id == entity_id
        ) or None
    return dump(_area_analysis(name, props, geometry=geometry, total_units=total_units))


@mcp.tool()
def gis_development_cost(entity_type: str, entity_id: str) -> str:
    """Development-cost estimate (land development, infrastructure, construction) for an entity."""
    analysis = json.loads(gis_area_analysis(entity_type, entity_id))
    return dump({"name": analysis["name"], "area": analysis["area"], "development_cost": analysis["development_cost"]})


@mcp.tool()
def gis_population_estimate(entity_type: str, entity_id: str) -> str:
    """Population, households and density estimate for an entity."""
    analysis = json.loads(gis_area_analysis(entity_type, entity_id))
    return dump({"name": analysis["name"], "area": analysis["area"], "population": analysis["population"]})


@mcp.tool()
def gis_economic_impact(entity_type: str, entity_id: str) -> str:
    """Economic-impact estimate (investment, output, jobs, tax, rental) for an entity."""
    analysis = json.loads(gis_area_analysis(entity_type, entity_id))
    return dump({"name": analysis["name"], "economic_impact": analysis["economic_impact"]})


@mcp.tool()
def gis_feature_table(scope_type: str, scope_id: str, metric: str = "population") -> str:
    """Prepare per-area features (a metric per scheme/block) for thematic maps and charts."""
    areas, info = _scope_areas(scope_type, scope_id)
    if areas is None:
        return dump({"error": f"Unknown scope type: {scope_type}"})
    if metric not in METRIC_LABELS:
        return dump({"error": f"Unknown metric: {metric}", "available": list(METRIC_LABELS)})
    rows = []
    for area in areas:
        analysis = _area_analysis(
            area["name"], area["properties"], geometry=area["geometry"], total_units=area["total_units"]
        )
        rows.append(
            {
                "name": area["name"],
                "entity_type": area["entity_type"],
                "entity_id": area["entity_id"],
                "value": _metric_value(analysis, metric),
                "property_count": analysis["properties"]["count"],
                "area_acres": analysis["area"]["area_acres"],
                "population": analysis["population"]["population_from_listings"],
                "market_value": analysis["properties"]["total_market_value"],
                "development_cost": analysis["development_cost"]["total"],
                "economic_output": analysis["economic_impact"]["total_economic_output"],
            }
        )
    rows.sort(key=lambda r: (r["value"] is None, -(r["value"] or 0)))
    return dump(
        {
            "scope": info,
            "metric": metric,
            "metric_label": METRIC_LABELS[metric],
            "count": len(rows),
            "features": rows,
        }
    )


@mcp.tool()
def gis_thematic_map(
    scope_type: str,
    scope_id: str,
    metric: str = "population",
    palette: str = "blues",
    classes: int = 5,
    base_map: Optional[str] = None,
    lang: str = gis.DEFAULT_LANGUAGE,
    theme: str = gis.DEFAULT_THEME,
) -> str:
    """Choropleth (thematic) map HTML for a metric across a city's schemes or a scheme's blocks.

    ``lang`` localises the map chrome (RTL supported) and ``theme`` picks the light/dark skin.
    """
    areas, info = _scope_areas(scope_type, scope_id)
    if areas is None:
        return dump({"error": f"Unknown scope type: {scope_type}"})
    if metric not in METRIC_LABELS:
        return dump({"error": f"Unknown metric: {metric}", "available": list(METRIC_LABELS)})

    features = []
    for area in areas:
        if not area["geometry"]:
            continue
        analysis = _area_analysis(
            area["name"], area["properties"], geometry=area["geometry"], total_units=area["total_units"]
        )
        value = _metric_value(analysis, metric)
        features.append(
            {
                "type": "Feature",
                "geometry": area["geometry"],
                "properties": {
                    "name": area["name"],
                    "entity_type": area["entity_type"],
                    "entity_id": area["entity_id"],
                    metric: value,
                    "description": (
                        f"Properties: {analysis['properties']['count']} · "
                        f"Value: {analysis['properties']['total_market_value']:,.0f} PKR"
                    ),
                },
            }
        )
    if not features:
        return dump({"error": "No mapped areas found for this scope"})

    meta = METRIC_LABELS[metric]
    overlay = gis.choropleth_overlay(
        name=f"{meta['label']} ({info['name']})",
        features=features,
        value_prop=metric,
        palette=palette,
        classes=classes,
        value_label=meta["label"],
        unit=meta["unit"],
    )
    box = gis.geojson_bbox({"type": "FeatureCollection", "features": features})
    lat = (box["south"] + box["north"]) / 2
    lon = (box["west"] + box["east"]) / 2
    return gis.build_map_html(
        title=f"{info['name']} — {meta['label']}",
        center_lat=lat,
        center_lon=lon,
        zoom=12,
        base_map_id=base_map or gis.DEFAULT_BASE_MAP,
        overlays=[overlay],
        lang=lang,
        theme=theme,
    )


@mcp.tool()
def gis_area_report(
    entity_type: str,
    entity_id: str,
    include_map: bool = True,
    include_outlook: bool = False,
    include_news: bool = False,
    years: int = 5,
    lang: str = gis.DEFAULT_LANGUAGE,
    theme: str = gis.DEFAULT_THEME,
) -> str:
    """Printable HTML report for an area: area, valuation, population, development cost, economics.

    Set ``include_outlook=True`` to append the cost/development perspective and multi-factor
    predictions, and ``include_news=True`` to embed a live real-estate news ticker.
    ``lang`` (English/Urdu, RTL) and ``theme`` (auto/light/dark) control the report UI.
    """
    props = _entity_properties(entity_type, entity_id)
    _, _, name = _entity_center(entity_type, entity_id)
    geometry = _entity_geometry(entity_type, entity_id, props)
    total_units = None
    city_id = entity_id if entity_type == "city" else None
    if entity_type == "scheme":
        s = find_scheme(entity_id)
        total_units = s.total_units if s else None
        city_id = s.city_id if s else None
    if entity_type == "block":
        b = find_block(entity_id)
        city_id = _scheme_city_id(b.scheme_id) if b else None
    analysis = _area_analysis(name, props, geometry=geometry, total_units=total_units)
    map_html = (
        gis_map_preview(entity_type, entity_id, lang=lang, theme=theme, lang_links=False)
        if include_map else None
    )

    sections = _report_sections(analysis)
    ticker = ""
    if include_outlook or include_news:
        scope_type, scope_id = _scope_for_entity(entity_type, entity_id)
        scores = _factor_dict(_find_factor(scope_type, scope_id))
        news_summary = _news_sentiment(city_id=city_id, scheme_id=entity_id if entity_type == "scheme" else None)
        news_items = _news_filter(city_id=city_id, scheme_id=entity_id if entity_type == "scheme" else None)[:12]
        if include_outlook:
            cost_dev = _cost_development_analysis(analysis, 0.0, total_units)
            forecast = _forecast(analysis, scores, news_summary, years=years)
            sections += _outlook_sections(analysis, cost_dev, forecast, news_summary, news_items)
        if include_news:
            ticker = gis.build_ticker_html([model_dict(n) for n in news_items], label="Real Estate News", lang=lang)

    return gis.build_report_html(
        title=f"{name} — {gis.translate('Report', lang)}",
        subtitle=f"{entity_type} · {analysis['area']['area_acres']:,.2f} acres · "
        f"{analysis['properties']['count']} properties · "
        f"{analysis['population']['population_from_listings']:,} people",
        sections=sections,
        map_html=map_html,
        ticker_html=ticker,
        lang=lang,
        theme=theme,
    )


# ---------- GIS analysis: cost/development, factors, forecasting, news ----------


def _scope_for_entity(entity_type: str, entity_id: str) -> tuple:
    if entity_type == "city":
        return "city", entity_id
    if entity_type == "scheme":
        return "scheme", entity_id
    if entity_type == "block":
        b = find_block(entity_id)
        if b:
            s = find_scheme(b.scheme_id)
            if s:
                return "scheme", s.id
            return "city", ""
    if entity_type == "bigproject":
        p = find_project(entity_id)
        if p:
            return "city", p.city_id
    return "national", "PK"


def _find_factor(scope_type: str, scope_id: str) -> Optional[MarketFactor]:
    f = next((x for x in factors_db if x.scope_type == scope_type and x.scope_id == scope_id), None)
    if f:
        return f
    return next((x for x in factors_db if x.scope_type == "national"), None)


def _factor_dict(f: Optional[MarketFactor]) -> Dict[str, float]:
    if not f:
        return {k: 55.0 for k in FACTOR_WEIGHTS}
    return {
        "development": f.development_score,
        "infrastructure": f.infrastructure_score,
        "economic": f.economic_score,
        "social": f.social_score,
        "political": f.political_score,
        "regulatory": f.regulatory_score,
        "demand": f.demand_score,
    }


def _composite_index(scores: Dict[str, float]) -> Dict[str, Any]:
    total = sum(scores.get(k, 50.0) * w for k, w in FACTOR_WEIGHTS.items())
    total = max(0.0, min(100.0, total))
    if total >= 75:
        band = "strong"
    elif total >= 60:
        band = "healthy"
    elif total >= 45:
        band = "moderate"
    elif total >= 30:
        band = "weak"
    else:
        band = "poor"
    return {"composite": round(total, 1), "band": band, "weights": FACTOR_WEIGHTS}


def _scheme_city_id(scheme_id: Optional[str]) -> Optional[str]:
    s = find_scheme(scheme_id) if scheme_id else None
    return s.city_id if s else None


def _news_filter(
    city_id: Optional[str] = None,
    scheme_id: Optional[str] = None,
    category: Optional[str] = None,
    sentiment: Optional[str] = None,
    channel_type: Optional[str] = None,
    days: Optional[int] = None,
    include_national: bool = True,
) -> List[NewsItem]:
    items = list(news_db)
    if city_id or scheme_id:
        scheme_city = _scheme_city_id(scheme_id) or city_id
        scoped = []
        for n in items:
            if scheme_id and n.scheme_id == scheme_id:
                scoped.append(n)
            elif city_id and n.city_id == city_id:
                scoped.append(n)
            elif include_national and n.city_id is None and n.scheme_id is None:
                scoped.append(n)
            elif scheme_id and n.city_id == scheme_city and n.scheme_id is None:
                scoped.append(n)
        items = scoped
    if category:
        items = [n for n in items if n.category == category]
    if sentiment:
        items = [n for n in items if n.sentiment == sentiment]
    if channel_type:
        items = [n for n in items if n.channel_type == channel_type]
    if days is not None:
        cutoff = datetime.now() - timedelta(days=days)
        items = [n for n in items if n.published_at >= cutoff]
    items.sort(key=lambda n: n.published_at, reverse=True)
    return items


def _news_sentiment(city_id: Optional[str] = None, scheme_id: Optional[str] = None, days: int = 120) -> Dict[str, Any]:
    items = _news_filter(city_id=city_id, scheme_id=scheme_id, days=days)
    if not items:
        return {
            "count": 0, "avg_impact": 0.0, "positive": 0, "neutral": 0, "negative": 0,
            "net_sentiment": "neutral", "momentum": 0.0,
        }
    avg = sum(n.impact_score for n in items) / len(items)
    pos = sum(1 for n in items if n.sentiment == "positive")
    neg = sum(1 for n in items if n.sentiment == "negative")
    neu = sum(1 for n in items if n.sentiment == "neutral")
    net = "positive" if avg > 5 else "negative" if avg < -5 else "neutral"
    return {
        "count": len(items),
        "avg_impact": round(avg, 1),
        "positive": pos,
        "neutral": neu,
        "negative": neg,
        "net_sentiment": net,
        "momentum": round(max(-0.5, min(0.5, avg / 100.0)), 3),
    }


def _cost_development_analysis(
    analysis: Dict[str, Any],
    sale_uplift: float = 0.0,
    total_units: Optional[int] = None,
    build_years: int = DEFAULT_BUILD_YEARS,
) -> Dict[str, Any]:
    m = analysis["properties"]
    cost = analysis["development_cost"]
    area = analysis["area"]
    econ = analysis["economic_impact"]

    gdv = m["total_market_value"] * (1 + sale_uplift)
    land_cost = m.get("plot_value", 0.0) or (gdv * LAND_COST_SHARE)
    total_cost = cost["total"] + land_cost
    profit = gdv - total_cost
    margin = (profit / gdv) if gdv else 0.0
    roi = (profit / total_cost) if total_cost else 0.0
    annualized = ((1 + roi) ** (1 / build_years) - 1) if roi > -1 else roi
    land_marla = m.get("marla_base") or area["area_marla"]
    breakeven_per_marla = (total_cost / land_marla) if land_marla else 0.0
    breakeven_uplift = ((total_cost / m["total_market_value"]) - 1) if m["total_market_value"] else 0.0
    rental = econ["annual_rental_value"] or 1.0
    payback = total_cost / rental

    if margin >= 0.25:
        viability = "strong"
    elif margin >= 0.15:
        viability = "viable"
    elif margin >= 0.05:
        viability = "marginal"
    else:
        viability = "unviable"

    price_deltas = [-0.20, -0.10, 0.0, 0.10, 0.20]
    cost_deltas = [-0.10, 0.0, 0.10]
    sensitivity = []
    for cd in cost_deltas:
        row = []
        for pd in price_deltas:
            g = gdv * (1 + pd)
            c = total_cost * (1 + cd)
            row.append(round((g - c) / g, 4) if g else 0.0)
        sensitivity.append({"cost_delta": cd, "price_deltas": price_deltas, "margins": row})

    phases = []
    for i in range(1, 5):
        capex = total_cost * 0.25
        phases.append({"phase": i, "share": 0.25, "capex": round(capex, 2), "cumulative": round(capex * i, 2)})

    projected = None
    dwellings = analysis["population"]["dwellings_listed"]
    if total_units and dwellings:
        scale = total_units / dwellings
        proj_gdv = m["total_market_value"] * scale
        proj_construction = cost["construction"] * scale
        proj_cost = cost["land_development"] + cost["infrastructure"] + proj_construction + land_cost
        projected = {
            "total_units": total_units,
            "gross_development_value": round(proj_gdv, 2),
            "total_cost": round(proj_cost, 2),
            "developer_profit": round(proj_gdv - proj_cost, 2),
            "profit_margin": round((proj_gdv - proj_cost) / proj_gdv, 4) if proj_gdv else 0.0,
            "cost_per_unit": round(proj_cost / total_units, 2) if total_units else 0.0,
            "value_per_unit": round(proj_gdv / total_units, 2) if total_units else 0.0,
        }

    return {
        "gross_development_value": round(gdv, 2),
        "total_cost": round(total_cost, 2),
        "cost_breakdown": {
            "land_cost": round(land_cost, 2),
            "land_development": cost["land_development"],
            "infrastructure": cost["infrastructure"],
            "construction": cost["construction"],
            "construction_by_category": cost["construction_by_category"],
        },
        "developer_profit": round(profit, 2),
        "profit_margin": round(margin, 4),
        "roi": round(roi, 4),
        "annualized_roi": round(annualized, 4),
        "build_years": build_years,
        "cost_per_sqft_of_land": cost["cost_per_sqft_of_land"],
        "cost_per_marla": round(total_cost / land_marla, 2) if land_marla else 0.0,
        "breakeven_price_per_marla": round(breakeven_per_marla, 2),
        "breakeven_uplift": round(breakeven_uplift, 4),
        "payback_years": round(payback, 1),
        "target_margin": None,
        "viability": viability,
        "sensitivity": sensitivity,
        "phasing": phases,
        "projected": projected,
    }


def _forecast(
    analysis: Dict[str, Any],
    scores: Dict[str, float],
    news: Dict[str, Any],
    years: int = 5,
) -> Dict[str, Any]:
    index = _composite_index(scores)
    momentum = news.get("momentum", 0.0)
    base_cagr = BASE_PRICE_CAGR + (index["composite"] - 50) / 100 * GROWTH_SENSITIVITY + momentum * 0.02
    base_cagr = max(-0.10, min(0.30, base_cagr))

    m = analysis["properties"]
    pop_block = analysis["population"]
    pop = (pop_block.get("projected") or {}).get("population") or pop_block["population_from_listings"]
    price_marla = m["price_per_marla"] or (m["total_market_value"] / m["count"] / 10 if m["count"] else 0)
    market_value = m["total_market_value"]
    rental = analysis["economic_impact"]["annual_rental_value"]
    cost = analysis["development_cost"]["total"]

    scenarios: Dict[str, Any] = {}
    expected_series: Dict[int, Dict[str, float]] = {}
    for key, cfg in SCENARIOS.items():
        cagr = max(-0.20, min(0.35, base_cagr + cfg["cagr_delta"]))
        rows = []
        for y in range(0, years + 1):
            row = {
                "year": datetime.now().year + y,
                "offset": y,
                "price_per_marla": round(price_marla * (1 + cagr) ** y, 2),
                "market_value": round(market_value * (1 + cagr) ** y, 2),
                "rental_value": round(rental * (1 + cagr) ** y, 2),
                "population": round(pop * (1 + (0.02 if key == "optimistic" else 0.015 if key == "base" else 0.005)) ** y),
                "development_cost": round(cost * (1 + COST_INFLATION_CAGR) ** y * cfg["cost_multiplier"], 2),
            }
            rows.append(row)
            if y not in expected_series:
                expected_series[y] = {"year": row["year"], "offset": y}
            for field in ("price_per_marla", "market_value", "rental_value", "population", "development_cost"):
                expected_series[y][field] = expected_series[y].get(field, 0.0) + row[field] * cfg["probability"]
        scenarios[key] = {
            "label": cfg["label"],
            "probability": cfg["probability"],
            "price_cagr": round(cagr, 4),
            "series": rows,
        }

    expected = []
    for y in sorted(expected_series):
        row = expected_series[y]
        expected.append({k: (round(v, 2) if k != "population" else round(v)) for k, v in row.items()})

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    drivers = [f"{k} ({v:.0f}/100)" for k, v in ranked[:3]]
    risks = [f"{k} ({v:.0f}/100)" for k, v in ranked[-2:] if v < 70]

    risk_flags = []
    if scores.get("political", 100) < 62:
        risk_flags.append("Political/regulatory instability may delay approvals or shift policy.")
    if scores.get("regulatory", 100) < 62:
        risk_flags.append("Weak regulatory/titling environment raises transaction risk.")
    if scores.get("infrastructure", 100) < 62:
        risk_flags.append("Infrastructure gaps limit near-term liveability and price upside.")
    if scores.get("economic", 100) < 62:
        risk_flags.append("Economic/mortgage conditions may dampen demand.")
    if news.get("net_sentiment") == "negative":
        risk_flags.append("Recent news sentiment is net negative for this market.")

    if index["band"] in ("strong", "healthy"):
        stance = "accumulate"
    elif index["band"] == "moderate":
        stance = "selective / hold"
    else:
        stance = "cautious / avoid near-term"

    recommendations = [
        f"Suggested stance: {stance}.",
        f"Plan on a base-case price CAGR of {scenarios['base']['price_cagr']:.1%} "
        f"(range {scenarios['pessimistic']['price_cagr']:.1%}–{scenarios['optimistic']['price_cagr']:.1%}).",
    ]
    if scores.get("demand", 100) >= 65:
        recommendations.append("Demand momentum is strong — phase releases to capture price growth.")
    if scores.get("development", 100) >= 70:
        recommendations.append("Heavy development pipeline: expect infrastructure-led appreciation.")

    confidence = 0.5 + min(0.28, m["count"] / 60.0) + (0.12 if news.get("count", 0) >= 3 else 0.0)
    confidence = round(min(0.95, confidence), 2)

    return {
        "horizon_years": years,
        "composite_index": index["composite"],
        "index_band": index["band"],
        "factors": {k: round(v, 1) for k, v in scores.items()},
        "weights": FACTOR_WEIGHTS,
        "news_momentum": momentum,
        "base_cagr": round(base_cagr, 4),
        "scenarios": scenarios,
        "expected": expected,
        "drivers": drivers,
        "risk_flags": risk_flags,
        "recommendations": recommendations,
        "confidence": confidence,
        "method": "composite factor index + news momentum + scenario shock model",
    }


def _outlook_sections(
    analysis: Dict[str, Any],
    cost_dev: Dict[str, Any],
    forecast: Dict[str, Any],
    news_summary: Dict[str, Any],
    news_items: List[NewsItem],
) -> List[Dict[str, Any]]:
    def money(v: float) -> str:
        return f"{v:,.0f}"

    sens_rows = []
    for row in cost_dev["sensitivity"]:
        sens_rows.append(
            [f"{row['cost_delta']:+.0%}"]
            + [f"{m:+.1%}" for m in row["margins"]]
        )

    proj = cost_dev.get("projected")
    cost_items = [
        ("Gross development value (PKR)", money(cost_dev["gross_development_value"])),
        ("Land cost (PKR)", money(cost_dev["cost_breakdown"]["land_cost"])),
        ("Development cost (PKR)", money(cost_dev["total_cost"] - cost_dev["cost_breakdown"]["land_cost"])),
        ("Total cost (PKR)", money(cost_dev["total_cost"])),
        ("Developer profit (PKR)", money(cost_dev["developer_profit"])),
        ("Profit margin", f"{cost_dev['profit_margin']:.1%}"),
        ("ROI (project)", f"{cost_dev['roi']:.1%}"),
        (f"Annualised ROI ({cost_dev['build_years']} yrs)", f"{cost_dev['annualized_roi']:.1%}"),
        ("Cost / marla (PKR)", money(cost_dev["cost_per_marla"])),
        ("Break-even price / marla (PKR)", money(cost_dev["breakeven_price_per_marla"])),
        ("Break-even uplift needed", f"{cost_dev['breakeven_uplift']:.1%}"),
        ("Payback (years, rental)", f"{cost_dev['payback_years']}"),
        ("Viability", cost_dev["viability"]),
    ]
    if proj:
        cost_items += [
            ("Projected units", f"{proj['total_units']:,}"),
            ("Projected GDV (PKR)", money(proj["gross_development_value"])),
            ("Projected cost (PKR)", money(proj["total_cost"])),
            ("Projected margin", f"{proj['profit_margin']:.1%}"),
            ("Cost / unit (PKR)", money(proj["cost_per_unit"])),
            ("Value / unit (PKR)", money(proj["value_per_unit"])),
        ]

    scenario_rows = []
    for key in ("optimistic", "base", "pessimistic", "stress"):
        sc = forecast["scenarios"][key]
        final = sc["series"][-1]
        scenario_rows.append(
            [
                sc["label"],
                f"{sc['probability']:.0%}",
                f"{sc['price_cagr']:.1%}",
                money(final["price_per_marla"]),
                money(final["market_value"]),
                money(final["development_cost"]),
            ]
        )

    expected_rows = [
        [
            str(r["year"]),
            money(r["price_per_marla"]),
            money(r["market_value"]),
            money(r["rental_value"]),
            f"{r['population']:,.0f}",
            money(r["development_cost"]),
        ]
        for r in forecast["expected"]
    ]

    return [
        {
            "heading": "Cost & development perspective",
            "kind": "kv",
            "items": cost_items,
        },
        {
            "heading": "Cost sensitivity — profit margin",
            "kind": "table",
            "columns": ["Cost \\ Price", "-20%", "-10%", "0%", "+10%", "+20%"],
            "numeric": ["-20%", "-10%", "0%", "+10%", "+20%"],
            "rows": sens_rows,
        },
        {
            "heading": "Market outlook index",
            "kind": "kv",
            "items": [("Composite index (0-100)", f"{forecast['composite_index']} ({forecast['index_band']})")]
            + [(f"  {k} factor", f"{v}/100") for k, v in forecast["factors"].items()]
            + [
                ("News momentum", f"{forecast['news_momentum']:+.3f}"),
                ("Base-case price CAGR", f"{forecast['base_cagr']:.1%}"),
                ("Model confidence", f"{forecast['confidence']:.0%}"),
            ],
        },
        {
            "heading": f"Future predictions — {forecast['horizon_years']}-year scenarios",
            "kind": "table",
            "columns": ["Scenario", "Prob.", "Price CAGR", "Price/marla", "Market value", "Dev. cost"],
            "numeric": ["Prob.", "Price CAGR", "Price/marla", "Market value", "Dev. cost"],
            "rows": scenario_rows,
        },
        {
            "heading": "Expected path (probability-weighted)",
            "kind": "table",
            "columns": ["Year", "Price/marla", "Market value", "Rental value", "Population", "Dev. cost"],
            "numeric": ["Price/marla", "Market value", "Rental value", "Population", "Dev. cost"],
            "rows": expected_rows,
        },
        {
            "heading": "Drivers",
            "kind": "pills",
            "items": forecast["drivers"],
        },
        {
            "heading": "Risks",
            "kind": "pills",
            "items": forecast["risk_flags"] or ["No material risk flags at current factor scores."],
        },
        {
            "heading": "Recommendations",
            "kind": "text",
            "text": " ".join(forecast["recommendations"]),
        },
        {
            "heading": "News & market sentiment",
            "kind": "kv",
            "items": [
                ("Items considered", f"{news_summary['count']}"),
                ("Average impact", f"{news_summary['avg_impact']:+.1f}"),
                ("Positive / neutral / negative", f"{news_summary['positive']} / {news_summary['neutral']} / {news_summary['negative']}"),
                ("Net sentiment", news_summary["net_sentiment"]),
            ],
        },
        {
            "heading": "Latest headlines",
            "kind": "news",
            "items": [
                {
                    "title": n.title,
                    "source": n.source,
                    "url": n.url,
                    "sentiment": n.sentiment,
                    "impact_score": n.impact_score,
                    "category": n.category,
                    "published_at": n.published_at.isoformat(),
                }
                for n in news_items[:12]
            ],
        },
    ]


@mcp.tool()
def gis_cost_development_analysis(
    entity_type: str,
    entity_id: str,
    sale_uplift: float = 0.0,
    build_years: int = DEFAULT_BUILD_YEARS,
) -> str:
    """Cost & development perspective: GDV, cost build-up, developer profit, ROI, break-even,
    sensitivity grid and phased capex. ``sale_uplift`` shifts assumed sale prices."""
    props = _entity_properties(entity_type, entity_id)
    _, _, name = _entity_center(entity_type, entity_id)
    total_units = None
    if entity_type == "scheme":
        s = find_scheme(entity_id)
        total_units = s.total_units if s else None
    analysis = _area_analysis(name, props, geometry=_entity_geometry(entity_type, entity_id, props), total_units=total_units)
    return dump(
        {
            "name": name,
            "area": analysis["area"],
            "development_cost": analysis["development_cost"],
            "cost_development": _cost_development_analysis(analysis, sale_uplift, total_units, build_years),
        }
    )


@mcp.tool()
def gis_market_factors(entity_type: str, entity_id: str) -> str:
    """Development / social / economic / political / regulatory factor scores for an area."""
    scope_type, scope_id = _scope_for_entity(entity_type, entity_id)
    factor = _find_factor(scope_type, scope_id)
    scores = _factor_dict(factor)
    return dump(
        {
            "scope": {"scope_type": scope_type, "scope_id": scope_id},
            "factors": {k: round(v, 1) for k, v in scores.items()},
            "weights": FACTOR_WEIGHTS,
            "index": _composite_index(scores),
            "notes": factor.notes if factor else None,
            "updated_at": factor.updated_at.isoformat() if factor else None,
        }
    )


@mcp.tool()
def gis_forecast(entity_type: str, entity_id: str, years: int = 5) -> str:
    """Future predictions for an area from development, social, economic and political factors,
    with optimistic / base / pessimistic / stress scenarios and a probability-weighted path."""
    props = _entity_properties(entity_type, entity_id)
    _, _, name = _entity_center(entity_type, entity_id)
    total_units = None
    city_id = entity_id if entity_type == "city" else None
    if entity_type == "scheme":
        s = find_scheme(entity_id)
        total_units = s.total_units if s else None
        city_id = s.city_id if s else None
    if entity_type == "block":
        b = find_block(entity_id)
        city_id = _scheme_city_id(b.scheme_id) if b else None

    analysis = _area_analysis(name, props, geometry=_entity_geometry(entity_type, entity_id, props), total_units=total_units)
    scope_type, scope_id = _scope_for_entity(entity_type, entity_id)
    scores = _factor_dict(_find_factor(scope_type, scope_id))
    news_summary = _news_sentiment(city_id=city_id, scheme_id=entity_id if entity_type == "scheme" else None)
    forecast = _forecast(analysis, scores, news_summary, years=years)
    return dump({"name": name, "scope": {"scope_type": scope_type, "scope_id": scope_id}, "forecast": forecast})


@mcp.tool()
def gis_scenario_analysis(entity_type: str, entity_id: str, years: int = 5) -> str:
    """Compare the optimistic / base / pessimistic / stress scenarios side by side."""
    result = json.loads(gis_forecast(entity_type, entity_id, years))
    return dump({"name": result["name"], "scenarios": result["forecast"]["scenarios"], "expected": result["forecast"]["expected"]})


# ---------- News ticker ----------


@mcp.tool()
def news_add(
    title: str,
    source: str,
    category: str = "market",
    sentiment: str = "neutral",
    impact_score: float = 0.0,
    channel_type: str = "news",
    summary: Optional[str] = None,
    url: Optional[str] = None,
    city_id: Optional[str] = None,
    scheme_id: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> str:
    """Add a news / announcement item that impacts real-estate sentiment.

    ``impact_score`` is -100 (very negative) .. +100 (very positive); leave it unset to
    derive a score from ``sentiment``.
    """
    if sentiment not in SENTIMENTS:
        return dump({"error": f"sentiment must be one of {SENTIMENTS}"})
    if category not in NEWS_CATEGORIES:
        return dump({"error": f"category must be one of {NEWS_CATEGORIES}"})
    if impact_score == 0.0:
        impact_score = {"positive": 40.0, "neutral": 0.0, "negative": -40.0}[sentiment]
    item = NewsItem(
        title=title,
        source=source,
        channel_type=channel_type,
        category=category,
        sentiment=sentiment,
        impact_score=impact_score,
        summary=summary,
        url=url,
        city_id=city_id,
        scheme_id=scheme_id,
        tags=tags or [],
    )
    news_db.append(item)
    return dump_model(item)


@mcp.tool()
def news_list(
    category: Optional[str] = None,
    city: Optional[str] = None,
    scheme: Optional[str] = None,
    sentiment: Optional[str] = None,
    channel_type: Optional[str] = None,
    days: Optional[int] = None,
    limit: int = 50,
) -> str:
    """List news items, filtered by category / city / scheme / sentiment / channel / recency."""
    city_id = resolve_city(city).id if city and resolve_city(city) else None
    scheme_id = None
    if scheme:
        s = find_scheme(scheme) or next((x for x in housing_schemes_db if x.name.lower() == scheme.lower()), None)
        scheme_id = s.id if s else None
    items = _news_filter(city_id=city_id, scheme_id=scheme_id, category=category, sentiment=sentiment, channel_type=channel_type, days=days)
    return dump({"count": len(items), "news": [model_dict(n) for n in items[:limit]]})


@mcp.tool()
def news_channels() -> str:
    """List news channels/sources with item counts and average impact."""
    by_source: Dict[str, Dict[str, Any]] = {}
    for n in news_db:
        row = by_source.setdefault(n.source, {"source": n.source, "channel_type": n.channel_type, "count": 0, "impact_sum": 0.0})
        row["count"] += 1
        row["impact_sum"] += n.impact_score
    out = []
    for row in by_source.values():
        out.append(
            {
                "source": row["source"],
                "channel_type": row["channel_type"],
                "count": row["count"],
                "avg_impact": round(row["impact_sum"] / row["count"], 1),
            }
        )
    out.sort(key=lambda r: -r["count"])
    return dump({"count": len(out), "channels": out})


@mcp.tool()
def news_impact(city: Optional[str] = None, scheme: Optional[str] = None, days: int = 120) -> str:
    """Aggregate news sentiment / impact for a market and how it feeds the outlook."""
    city_id = resolve_city(city).id if city and resolve_city(city) else None
    scheme_id = None
    if scheme:
        s = find_scheme(scheme)
        scheme_id = s.id if s else None
    summary = _news_sentiment(city_id=city_id, scheme_id=scheme_id, days=days)
    by_category: Dict[str, Dict[str, float]] = {}
    for n in _news_filter(city_id=city_id, scheme_id=scheme_id, days=days):
        row = by_category.setdefault(n.category, {"count": 0, "impact_sum": 0.0})
        row["count"] += 1
        row["impact_sum"] += n.impact_score
    return dump(
        {
            "city_id": city_id,
            "scheme_id": scheme_id,
            "days": days,
            "summary": summary,
            "by_category": {
                k: {"count": int(v["count"]), "avg_impact": round(v["impact_sum"] / v["count"], 1)}
                for k, v in sorted(by_category.items())
            },
            "effect_on_outlook": {
                "momentum": summary["momentum"],
                "interpretation": (
                    "raises" if summary["momentum"] > 0.05 else "lowers" if summary["momentum"] < -0.05 else "neutral on"
                )
                + " the projected price CAGR",
            },
        }
    )


@mcp.tool()
def news_ticker(
    category: Optional[str] = None,
    city: Optional[str] = None,
    scheme: Optional[str] = None,
    limit: int = 25,
    speed_seconds: float = 70.0,
    label: str = "Real Estate News",
    lang: str = gis.DEFAULT_LANGUAGE,
) -> str:
    """Render a self-contained scrolling news-ticker (HTML) of real-estate-relevant headlines.

    ``lang`` localises the ticker label and sets the text direction (Urdu is RTL).
    """
    city_id = resolve_city(city).id if city and resolve_city(city) else None
    scheme_id = None
    if scheme:
        s = find_scheme(scheme)
        scheme_id = s.id if s else None
    items = _news_filter(city_id=city_id, scheme_id=scheme_id, category=category)[:limit]
    html_out = gis.build_ticker_html([model_dict(n) for n in items], label=label, speed_seconds=speed_seconds, lang=lang)
    if not html_out:
        return dump({"error": "No news items match the filter"})
    return html_out


@mcp.tool()
def gis_outlook_report(
    entity_type: str,
    entity_id: str,
    years: int = 5,
    include_map: bool = True,
    include_news: bool = True,
    lang: str = gis.DEFAULT_LANGUAGE,
    theme: str = gis.DEFAULT_THEME,
) -> str:
    """Printable HTML outlook report: area + valuation + cost/development + predictions
    (development/social/economic/political) + a live news ticker.

    ``lang`` (English/Urdu, RTL) and ``theme`` (auto/light/dark) control the report UI.
    """
    props = _entity_properties(entity_type, entity_id)
    _, _, name = _entity_center(entity_type, entity_id)
    geometry = _entity_geometry(entity_type, entity_id, props)
    total_units = None
    city_id = entity_id if entity_type == "city" else None
    if entity_type == "scheme":
        s = find_scheme(entity_id)
        total_units = s.total_units if s else None
        city_id = s.city_id if s else None
    if entity_type == "block":
        b = find_block(entity_id)
        city_id = _scheme_city_id(b.scheme_id) if b else None

    analysis = _area_analysis(name, props, geometry=geometry, total_units=total_units)
    cost_dev = _cost_development_analysis(analysis, 0.0, total_units)
    scope_type, scope_id = _scope_for_entity(entity_type, entity_id)
    scores = _factor_dict(_find_factor(scope_type, scope_id))
    news_summary = _news_sentiment(city_id=city_id, scheme_id=entity_id if entity_type == "scheme" else None)
    forecast = _forecast(analysis, scores, news_summary, years=years)
    news_items = _news_filter(city_id=city_id, scheme_id=entity_id if entity_type == "scheme" else None)[:12]

    sections = _report_sections(analysis) + _outlook_sections(analysis, cost_dev, forecast, news_summary, news_items)
    ticker = gis.build_ticker_html([model_dict(n) for n in news_items], label="Real Estate News", lang=lang) if include_news else ""
    return gis.build_report_html(
        title=f"{name} — {gis.translate('Investment Outlook', lang)}",
        subtitle=f"{entity_type} · index {forecast['composite_index']} ({forecast['index_band']}) · "
        f"base CAGR {forecast['base_cagr']:.1%} · margin {cost_dev['profit_margin']:.1%}",
        sections=sections,
        map_html=gis_map_preview(entity_type, entity_id, lang=lang, theme=theme, lang_links=False) if include_map else None,
        ticker_html=ticker,
        lang=lang,
        theme=theme,
    )


# ---------- Memory layers ----------


@mcp.tool()
def memory_store(operation: str, key: Optional[str] = None, value: Optional[str] = None) -> str:
    """Manage memory. operations: add_near | add_favorite | set_preference | clear."""
    if operation == "add_near":
        remember("manual", value or key)
        return dump({"stored": True, "near_size": len(near_memory_cache)})
    if operation == "add_favorite":
        target = value or key
        if target and target not in long_term_memory["favorites"]:
            long_term_memory["favorites"].append(target)
        return dump({"favorites": long_term_memory["favorites"]})
    if operation == "set_preference":
        if key is None:
            return dump({"error": "key required for set_preference"})
        long_term_memory["preferences"][key] = value
        return dump({"preferences": long_term_memory["preferences"]})
    if operation == "clear":
        near_memory_cache.clear()
        long_term_memory["search_history"].clear()
        long_term_memory["property_views"].clear()
        long_term_memory["favorites"].clear()
        long_term_memory["preferences"].clear()
        return dump({"cleared": True})
    return dump({"error": f"Unknown operation: {operation}"})


@mcp.tool()
def memory_retrieve(key: str) -> str:
    """Retrieve a value from long-term memory (favorites, views, preferences) or near cache."""
    if key in long_term_memory:
        return dump({"key": key, "value": long_term_memory[key]})
    if key in long_term_memory["preferences"]:
        return dump({"key": key, "value": long_term_memory["preferences"][key]})
    if key in long_term_memory["property_views"]:
        return dump({"key": key, "value": long_term_memory["property_views"][key]})
    recent = [n for n in near_memory_cache if n["kind"] == key]
    return dump({"key": key, "near_matches": recent})


@mcp.tool()
def get_memory_analytics() -> str:
    """Summarise the memory layers (cache size, searches, views, favourites)."""
    return dump(
        {
            "near_memory": {"size": len(near_memory_cache), "max": MAX_NEAR_MEMORY_SIZE, "items": near_memory_cache[-10:]},
            "long_term_memory": {
                "searches": len(long_term_memory["search_history"]),
                "recent_searches": long_term_memory["search_history"][-5:],
                "properties_viewed": len(long_term_memory["property_views"]),
                "top_viewed": sorted(
                    long_term_memory["property_views"].items(), key=lambda kv: kv[1], reverse=True
                )[:5],
                "favorites": long_term_memory["favorites"],
                "preferences": long_term_memory["preferences"],
            },
        }
    )


@mcp.tool()
def memory_clear() -> str:
    """Clear every memory layer."""
    near_memory_cache.clear()
    long_term_memory["search_history"].clear()
    long_term_memory["property_views"].clear()
    long_term_memory["favorites"].clear()
    long_term_memory["preferences"].clear()
    return dump({"cleared": True})


# ---------- RAG & insights ----------


def _rag_documents() -> List[Dict[str, Any]]:
    docs: List[Dict[str, Any]] = []
    for p in properties_db:
        text = " ".join(
            filter(
                None,
                [
                    p.title,
                    p.description,
                    p.use_type,
                    p.category,
                    city_name(p.city_id),
                    (find_scheme(p.scheme_id).name if find_scheme(p.scheme_id) else ""),
                    p.sector,
                    p.landmark,
                    f"{p.bedrooms} bedroom" if p.bedrooms else "",
                ],
            )
        )
        docs.append({"id": p.id, "type": "property", "text": text, "ref": p})
    for s in housing_schemes_db:
        docs.append(
            {
                "id": s.id,
                "type": "scheme",
                "text": f"{s.name} {s.description or ''} {city_name(s.city_id)}",
                "ref": s,
            }
        )
    for b in big_projects_db:
        docs.append(
            {
                "id": b.id,
                "type": "big_project",
                "text": f"{b.name} {b.description or ''} {b.project_type} {city_name(b.city_id)}",
                "ref": b,
            }
        )
    return docs


def _tokens(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


@mcp.tool()
def rag_search(query: str, top_k: int = 5) -> str:
    """Natural-language retrieval over properties, schemes and big projects."""
    q_tokens = _tokens(query)
    q_set = set(q_tokens)

    # Light structured parsing
    max_price = None
    m = re.search(r"(?:under|below|less than|max|upto|up to)\s*([\d,]+)", query.lower())
    if m:
        max_price = float(m.group(1).replace(",", ""))
    bed_match = re.search(r"(\d+)\s*(?:bed|bedroom|br\b)", query.lower())
    min_bedrooms = int(bed_match.group(1)) if bed_match else None

    docs = _rag_documents()
    scored = []
    for d in docs:
        d_tokens = _tokens(d["text"])
        if not d_tokens:
            continue
        overlap = q_set.intersection(d_tokens)
        if not overlap:
            continue
        # simple tf-weighted cosine-ish score
        score = sum(d_tokens.count(tok) for tok in overlap) / (1 + math.log(1 + len(d_tokens)))
        score += 0.5 * len(overlap) / max(1, len(q_set))
        ref = d["ref"]
        if max_price is not None and isinstance(ref, Property) and ref.price > max_price:
            continue
        if min_bedrooms is not None and isinstance(ref, Property) and (ref.bedrooms or 0) < min_bedrooms:
            continue
        scored.append((round(score, 4), d))

    scored.sort(key=lambda x: x[0], reverse=True)
    hits = []
    for score, d in scored[: max(1, top_k)]:
        item = {"score": score, "type": d["type"], "id": d["id"]}
        if d["type"] == "property":
            p = d["ref"]
            item.update(
                {
                    "title": p.title,
                    "price": p.price,
                    "city": city_name(p.city_id),
                    "use_type": p.use_type,
                    "category": p.category,
                    "marla": p.marla_area,
                    "bedrooms": p.bedrooms,
                }
            )
        else:
            item["name"] = d["ref"].name
            item["city"] = city_name(d["ref"].city_id)
        hits.append(item)

    context = "\n".join(
        f"- [{h['type']}] {h.get('title') or h.get('name')} ({h.get('city')})"
        for h in hits
    )
    long_term_memory["search_history"].append({"at": datetime.now().isoformat(), "rag": query, "results": len(hits)})
    remember("rag", {"query": query, "results": len(hits)})
    return dump({"query": query, "count": len(hits), "results": hits, "context": context})


@mcp.tool()
def investment_analysis(property_id: str) -> str:
    """Price/sqft, price/marla and market comparison for a property."""
    p = find_property(property_id)
    if not p:
        return dump({"error": f"Property not found: {property_id}"})
    city_props = [x for x in properties_db if x.city_id == p.city_id and x.total_area]
    city_avg_sqft = (
        round(sum(x.price / x.total_area for x in city_props) / len(city_props), 2) if city_props else None
    )
    price_per_sqft = round(p.price / p.total_area, 2) if p.total_area else None
    price_per_marla = round(p.price / p.marla_area, 2) if p.marla_area else None
    delta_pct = (
        round((price_per_sqft - city_avg_sqft) / city_avg_sqft * 100, 1)
        if price_per_sqft and city_avg_sqft
        else None
    )

    # crude rental yield using 0.35% of value / month (4.2% annual)
    monthly_rent = round(p.price * 0.0035, 2)
    annual_yield = round((monthly_rent * 12) / p.price * 100, 2) if p.price else None

    if delta_pct is None:
        verdict = "insufficient comparable data"
    elif delta_pct <= -10:
        verdict = "undervalued vs city average"
    elif delta_pct >= 10:
        verdict = "premium priced vs city average"
    else:
        verdict = "in line with city average"

    return dump(
        {
            "property": {"id": p.id, "title": p.title, "city": city_name(p.city_id)},
            "price": p.price,
            "price_per_sqft": price_per_sqft,
            "price_per_marla": price_per_marla,
            "city_avg_price_per_sqft": city_avg_sqft,
            "delta_vs_city_pct": delta_pct,
            "verdict": verdict,
            "estimated_monthly_rent": monthly_rent,
            "estimated_gross_yield_pct": annual_yield,
        }
    )


@mcp.tool()
def market_insights(city: str) -> str:
    """Aggregate market statistics for a city."""
    c = resolve_city(city)
    if not c:
        return dump({"error": f"City not found: {city}"})
    props = [p for p in properties_db if p.city_id == c.id]
    if not props:
        return dump({"city": c.name, "properties": 0})
    prices = [p.price for p in props]
    per_sqft = [p.price / p.total_area for p in props if p.total_area]
    by_category: Dict[str, int] = {}
    by_use: Dict[str, int] = {}
    for p in props:
        by_category[p.category] = by_category.get(p.category, 0) + 1
        by_use[p.use_type] = by_use.get(p.use_type, 0) + 1
    return dump(
        {
            "city": c.name,
            "properties": len(props),
            "avg_price": round(sum(prices) / len(prices), 2),
            "min_price": min(prices),
            "max_price": max(prices),
            "avg_price_per_sqft": round(sum(per_sqft) / len(per_sqft), 2) if per_sqft else None,
            "by_category": by_category,
            "by_use_type": by_use,
            "schemes": len([s for s in housing_schemes_db if s.city_id == c.id]),
            "big_projects": len([b for b in big_projects_db if b.city_id == c.id]),
        }
    )


# ---------- Big projects ----------


@mcp.tool()
def add_big_project(
    name: str,
    city_id: str,
    project_type: str = PROJECT_TYPE_MALL,
    description: Optional[str] = None,
    status: str = "planned",
    floor_count: int = 0,
    total_area: Optional[float] = None,
    total_units: Optional[int] = None,
    scheme_id: Optional[str] = None,
    block_zone_area_id: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    developer: Optional[str] = None,
    start_date: Optional[str] = None,
    completion_date: Optional[str] = None,
) -> str:
    """Create a big project (mall, tower, mixed-use, compound, plaza, office complex)."""
    if not find_city(city_id):
        return dump({"error": f"City not found: {city_id}"})
    b = BigProject(
        name=name,
        city_id=city_id,
        project_type=project_type,
        description=description,
        status=status,
        floor_count=floor_count,
        total_area=total_area,
        total_units=total_units,
        scheme_id=scheme_id,
        block_zone_area_id=block_zone_area_id,
        latitude=latitude,
        longitude=longitude,
        developer=developer,
        start_date=start_date,
        completion_date=completion_date,
    )
    big_projects_db.append(b)
    return dump_model(b)


@mcp.tool()
def get_big_project_by_id(project_id: str) -> str:
    """Fetch a big project by id."""
    b = find_project(project_id)
    if not b:
        return dump({"error": f"Big project not found: {project_id}"})
    data = model_dict(b)
    data["city_name"] = city_name(b.city_id)
    return dump(data)


@mcp.tool()
def list_big_projects(city: Optional[str] = None, project_type: Optional[str] = None) -> str:
    """List big projects, filtered by city and/or type."""
    c = resolve_city(city) if city else None
    out = []
    for b in big_projects_db:
        if c and b.city_id != c.id:
            continue
        if project_type and b.project_type != project_type:
            continue
        out.append(
            {
                "id": b.id,
                "name": b.name,
                "project_type": b.project_type,
                "status": b.status,
                "city": city_name(b.city_id),
                "floor_count": b.floor_count,
                "total_area": b.total_area,
                "occupancy_rate": b.occupancy_rate,
            }
        )
    return dump({"count": len(out), "projects": out})


@mcp.tool()
def update_big_project(
    project_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    status: Optional[str] = None,
    floor_count: Optional[int] = None,
    total_area: Optional[float] = None,
    total_units: Optional[int] = None,
    occupancy_rate: Optional[float] = None,
    developer: Optional[str] = None,
    completion_date: Optional[str] = None,
    total_parking_spaces: Optional[int] = None,
    total_retail_space: Optional[float] = None,
    total_office_space: Optional[float] = None,
    total_residential_units: Optional[int] = None,
) -> str:
    """Update editable fields of a big project."""
    b = find_project(project_id)
    if not b:
        return dump({"error": f"Big project not found: {project_id}"})
    fields = {
        "name": name,
        "description": description,
        "status": status,
        "floor_count": floor_count,
        "total_area": total_area,
        "total_units": total_units,
        "occupancy_rate": occupancy_rate,
        "developer": developer,
        "completion_date": completion_date,
        "total_parking_spaces": total_parking_spaces,
        "total_retail_space": total_retail_space,
        "total_office_space": total_office_space,
        "total_residential_units": total_residential_units,
    }
    for key, value in fields.items():
        if value is not None:
            setattr(b, key, value)
    b.updated_at = datetime.now()
    return dump_model(b)


@mcp.tool()
def delete_big_project(project_id: str) -> str:
    """Delete a big project by id."""
    b = find_project(project_id)
    if not b:
        return dump({"error": f"Big project not found: {project_id}"})
    big_projects_db.remove(b)
    image_storage["bigproject"].pop(project_id, None)
    return dump({"deleted": True, "project_id": project_id, "remaining": len(big_projects_db)})


def _project_add_media(project_id: str, field: str, value: str) -> str:
    b = find_project(project_id)
    if not b:
        return dump({"error": f"Big project not found: {project_id}"})
    getattr(b, field).append(value)
    b.updated_at = datetime.now()
    return dump({"project_id": project_id, field: value and getattr(b, field)})


@mcp.tool()
def add_project_map(project_id: str, map_url: str) -> str:
    """Attach a map/location image to a big project."""
    return _project_add_media(project_id, "maps", map_url)


@mcp.tool()
def add_project_floor_plan(project_id: str, floor_plan_url: str) -> str:
    """Attach a floor plan to a big project."""
    return _project_add_media(project_id, "floor_plans", floor_plan_url)


@mcp.tool()
def add_project_amenity(project_id: str, amenity: str) -> str:
    """Add an amenity to a big project."""
    return _project_add_media(project_id, "amenities", amenity)


@mcp.tool()
def add_project_multimedia(project_id: str, media_type: str, url: str) -> str:
    """Attach multimedia (e.g. video/VR/drone) to a big project."""
    b = find_project(project_id)
    if not b:
        return dump({"error": f"Big project not found: {project_id}"})
    b.multimedia.setdefault(media_type, []).append(url)
    b.updated_at = datetime.now()
    return dump({"project_id": project_id, "multimedia": b.multimedia})


# ---------- Images ----------


@mcp.tool()
def image_store(
    entity_type: str,
    entity_id: str,
    image_url: str,
    description: Optional[str] = None,
    is_primary: bool = False,
) -> str:
    """Store an image URL against any entity (city, scheme, block, property, bigproject, agent)."""
    if entity_type not in image_storage:
        return dump({"error": f"entity_type must be one of {list(image_storage)}"})
    if not validate_image_url(image_url):
        return dump({"error": f"Invalid image URL (expected image extension): {image_url}"})
    bucket = image_storage[entity_type].setdefault(entity_id, [])
    bucket.append(
        {
            "url": image_url,
            "description": description,
            "is_primary": is_primary,
            "added_at": datetime.now().isoformat(),
        }
    )
    return dump({"entity_type": entity_type, "entity_id": entity_id, "image_url": image_url, "count": len(bucket)})


@mcp.tool()
def image_list(entity_type: str, entity_id: Optional[str] = None) -> str:
    """List images for one entity or the whole entity type."""
    if entity_type not in image_storage:
        return dump({"error": f"entity_type must be one of {list(image_storage)}"})
    bucket = image_storage[entity_type]
    if entity_id:
        return dump({"entity_type": entity_type, "entity_id": entity_id, "images": bucket.get(entity_id, [])})
    return dump({"entity_type": entity_type, "total_entities": len(bucket), "images": bucket})


@mcp.tool()
def image_delete(entity_type: str, entity_id: str, image_index: int = 0) -> str:
    """Delete an image by index from an entity's gallery."""
    bucket = image_storage.get(entity_type, {})
    images = bucket.get(entity_id)
    if not images:
        return dump({"error": "No images found for that entity"})
    if not 0 <= image_index < len(images):
        return dump({"error": f"image_index out of range (0..{len(images) - 1})"})
    images.pop(image_index)
    if not images:
        bucket.pop(entity_id, None)
    return dump({"deleted": True, "entity_type": entity_type, "entity_id": entity_id, "remaining": len(images)})


@mcp.tool()
def image_set_primary(entity_type: str, entity_id: str, image_index: int = 0) -> str:
    """Mark one image as the primary image for an entity."""
    images = image_storage.get(entity_type, {}).get(entity_id, [])
    if not 0 <= image_index < len(images):
        return dump({"error": "Image not found"})
    for i, img in enumerate(images):
        img["is_primary"] = i == image_index
    return dump({"entity_id": entity_id, "primary_index": image_index})


# ============================================================
# CRM TOOLS
# ============================================================


def _find_agent(agent_id: Optional[str]) -> Optional[Agent]:
    return next((a for a in agents_db if a.id == agent_id), None)


def _find_lead(lead_id: Optional[str]) -> Optional[Lead]:
    return next((l for l in leads_db if l.id == lead_id), None)


def _find_customer(customer_id: Optional[str]) -> Optional[Customer]:
    return next((c for c in customers_db if c.id == customer_id), None)


def _find_deal(deal_id: str) -> Optional[Deal]:
    return next((d for d in deals_db if d.id == deal_id), None)


# ---- Agents ----


@mcp.tool()
def crm_add_agent(
    name: str,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    region: Optional[str] = None,
    specialization: Optional[str] = None,
    commission_rate: float = 0.02,
) -> str:
    """Create a sales agent."""
    a = Agent(
        name=name,
        email=email,
        phone=phone,
        region=region,
        specialization=specialization,
        commission_rate=commission_rate,
    )
    agents_db.append(a)
    return dump_model(a)


@mcp.tool()
def crm_list_agents(active_only: bool = False) -> str:
    """List sales agents."""
    out = [model_dict(a) for a in agents_db if (a.active or not active_only)]
    return dump({"count": len(out), "agents": out})


@mcp.tool()
def crm_get_agent(agent_id: str) -> str:
    """Get a single agent plus their pipeline totals."""
    a = _find_agent(agent_id)
    if not a:
        return dump({"error": f"Agent not found: {agent_id}"})
    deals = [d for d in deals_db if d.agent_id == agent_id]
    return dump(
        {
            "agent": model_dict(a),
            "leads": len([l for l in leads_db if l.assigned_agent_id == agent_id]),
            "deals": len(deals),
            "pipeline_value": sum(d.amount for d in deals if not d.stage.startswith("closed")),
        }
    )


@mcp.tool()
def crm_update_agent(
    agent_id: str,
    name: Optional[str] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    region: Optional[str] = None,
    specialization: Optional[str] = None,
    active: Optional[bool] = None,
    rating: Optional[float] = None,
    commission_rate: Optional[float] = None,
) -> str:
    """Update a sales agent."""
    a = _find_agent(agent_id)
    if not a:
        return dump({"error": f"Agent not found: {agent_id}"})
    for key, value in {
        "name": name,
        "email": email,
        "phone": phone,
        "region": region,
        "specialization": specialization,
        "active": active,
        "rating": rating,
        "commission_rate": commission_rate,
    }.items():
        if value is not None:
            setattr(a, key, value)
    return dump_model(a)


# ---- Leads ----


@mcp.tool()
def crm_add_lead(
    name: str,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    source: str = "website",
    interest_use_type: Optional[str] = None,
    interest_category: Optional[str] = None,
    budget_min: Optional[float] = None,
    budget_max: Optional[float] = None,
    city_id: Optional[str] = None,
    scheme_id: Optional[str] = None,
    assigned_agent_id: Optional[str] = None,
    notes: Optional[str] = None,
) -> str:
    """Create a sales lead with an optional property interest."""
    lead = Lead(
        name=name,
        email=email,
        phone=phone,
        source=source,
        interest_use_type=interest_use_type,
        interest_category=interest_category,
        budget_min=budget_min,
        budget_max=budget_max,
        city_id=city_id,
        scheme_id=scheme_id,
        assigned_agent_id=assigned_agent_id,
        notes=notes,
    )
    # Automatically match properties to score the lead.
    lead.score = _score_lead(lead)
    leads_db.append(lead)
    return dump_model(lead)


def _score_lead(lead: Lead) -> int:
    score = 20
    if lead.budget_max:
        score += 20
    if lead.interest_use_type:
        score += 10
    if lead.interest_category:
        score += 10
    if lead.city_id:
        score += 15
    if lead.phone:
        score += 15
    if lead.email:
        score += 10
    score += min(20, _match_properties_for_lead(lead, limit=1)["count"])
    return min(100, score)


def _match_properties_for_lead(lead: Lead, limit: int = 5) -> Dict[str, Any]:
    matches = []
    for p in properties_db:
        if lead.city_id and p.city_id != lead.city_id:
            continue
        if lead.scheme_id and p.scheme_id != lead.scheme_id:
            continue
        if lead.interest_use_type and p.use_type.lower() != lead.interest_use_type.lower():
            continue
        if lead.interest_category and p.category.lower() != lead.interest_category.lower():
            continue
        if lead.budget_min is not None and p.price < lead.budget_min:
            continue
        if lead.budget_max is not None and p.price > lead.budget_max:
            continue
        matches.append(p)
    return {"count": len(matches), "properties": [model_dict(p) for p in matches[:limit]]}


@mcp.tool()
def crm_list_leads(
    status: Optional[str] = None,
    agent_id: Optional[str] = None,
    city: Optional[str] = None,
    min_score: Optional[int] = None,
) -> str:
    """List leads with optional filters."""
    c = resolve_city(city) if city else None
    out = []
    for l in leads_db:
        if status and l.status != status:
            continue
        if agent_id and l.assigned_agent_id != agent_id:
            continue
        if c and l.city_id != c.id:
            continue
        if min_score is not None and l.score < min_score:
            continue
        d = model_dict(l)
        d["city_name"] = city_name(l.city_id) if l.city_id else None
        d["agent_name"] = (_find_agent(l.assigned_agent_id).name if _find_agent(l.assigned_agent_id) else None)
        out.append(d)
    return dump({"count": len(out), "leads": out})


@mcp.tool()
def crm_get_lead(lead_id: str) -> str:
    """Get a lead with matched properties, interactions and deals."""
    l = _find_lead(lead_id)
    if not l:
        return dump({"error": f"Lead not found: {lead_id}"})
    return dump(
        {
            "lead": model_dict(l),
            "matches": _match_properties_for_lead(l),
            "interactions": [model_dict(i) for i in interactions_db if i.entity_id == lead_id],
            "deals": [model_dict(d) for d in deals_db if d.lead_id == lead_id],
        }
    )


@mcp.tool()
def crm_update_lead(
    lead_id: str,
    status: Optional[str] = None,
    score: Optional[int] = None,
    assigned_agent_id: Optional[str] = None,
    budget_min: Optional[float] = None,
    budget_max: Optional[float] = None,
    notes: Optional[str] = None,
) -> str:
    """Update a lead."""
    l = _find_lead(lead_id)
    if not l:
        return dump({"error": f"Lead not found: {lead_id}"})
    if status and status not in LEAD_STATUSES:
        return dump({"error": f"status must be one of {LEAD_STATUSES}"})
    for key, value in {
        "status": status,
        "score": score,
        "assigned_agent_id": assigned_agent_id,
        "budget_min": budget_min,
        "budget_max": budget_max,
        "notes": notes,
    }.items():
        if value is not None:
            setattr(l, key, value)
    l.updated_at = datetime.now()
    return dump_model(l)


@mcp.tool()
def crm_assign_lead(lead_id: str, agent_id: str) -> str:
    """Assign a lead to an agent."""
    l, a = _find_lead(lead_id), _find_agent(agent_id)
    if not l:
        return dump({"error": f"Lead not found: {lead_id}"})
    if not a:
        return dump({"error": f"Agent not found: {agent_id}"})
    l.assigned_agent_id = agent_id
    l.updated_at = datetime.now()
    return dump({"lead_id": lead_id, "agent_id": agent_id, "agent_name": a.name})


@mcp.tool()
def crm_convert_lead(lead_id: str, customer_type: str = "buyer") -> str:
    """Convert a won lead into a customer."""
    l = _find_lead(lead_id)
    if not l:
        return dump({"error": f"Lead not found: {lead_id}"})
    customer = Customer(
        name=l.name,
        email=l.email,
        phone=l.phone,
        type=customer_type,
        city_id=l.city_id,
        source_lead_id=l.id,
        assigned_agent_id=l.assigned_agent_id,
        notes=l.notes,
    )
    customers_db.append(customer)
    l.status = "won"
    l.converted_customer_id = customer.id
    l.updated_at = datetime.now()
    return dump({"lead_id": lead_id, "customer": model_dict(customer)})


# ---- Customers ----


@mcp.tool()
def crm_add_customer(
    name: str,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    type: str = "buyer",
    city_id: Optional[str] = None,
    assigned_agent_id: Optional[str] = None,
    notes: Optional[str] = None,
) -> str:
    """Create a customer/contact directly."""
    c = Customer(
        name=name,
        email=email,
        phone=phone,
        type=type,
        city_id=city_id,
        assigned_agent_id=assigned_agent_id,
        notes=notes,
    )
    customers_db.append(c)
    return dump_model(c)


@mcp.tool()
def crm_list_customers(type: Optional[str] = None) -> str:
    """List customers, optionally filtered by type."""
    out = [model_dict(c) for c in customers_db if not type or c.type == type]
    return dump({"count": len(out), "customers": out})


@mcp.tool()
def crm_get_customer(customer_id: str) -> str:
    """Get a customer plus their deals and interactions."""
    c = _find_customer(customer_id)
    if not c:
        return dump({"error": f"Customer not found: {customer_id}"})
    return dump(
        {
            "customer": model_dict(c),
            "deals": [model_dict(d) for d in deals_db if d.customer_id == customer_id],
            "interactions": [model_dict(i) for i in interactions_db if i.entity_id == customer_id],
        }
    )


# ---- Interactions ----


@mcp.tool()
def crm_log_interaction(
    entity_type: str,
    entity_id: str,
    summary: str,
    channel: str = "call",
    direction: str = "outbound",
    agent_id: Optional[str] = None,
) -> str:
    """Log an interaction against a lead/customer/deal."""
    i = Interaction(
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary,
        channel=channel,
        direction=direction,
        agent_id=agent_id,
    )
    interactions_db.append(i)
    return dump_model(i)


@mcp.tool()
def crm_list_interactions(entity_id: str) -> str:
    """List interactions for a given entity."""
    out = [model_dict(i) for i in interactions_db if i.entity_id == entity_id]
    return dump({"count": len(out), "interactions": out})


# ---- Deals ----


@mcp.tool()
def crm_create_deal(
    title: str,
    amount: float,
    lead_id: Optional[str] = None,
    customer_id: Optional[str] = None,
    property_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    stage: str = "prospecting",
    probability: int = 20,
    expected_close_date: Optional[str] = None,
) -> str:
    """Create a deal in the sales pipeline."""
    if stage not in DEAL_STAGES:
        return dump({"error": f"stage must be one of {DEAL_STAGES}"})
    commission = 0.0
    a = _find_agent(agent_id)
    if a:
        commission = round(amount * a.commission_rate, 2)
    d = Deal(
        title=title,
        amount=amount,
        lead_id=lead_id,
        customer_id=customer_id,
        property_id=property_id,
        agent_id=agent_id,
        stage=stage,
        probability=probability,
        commission=commission,
        expected_close_date=expected_close_date,
    )
    deals_db.append(d)
    return dump_model(d)


@mcp.tool()
def crm_list_deals(stage: Optional[str] = None, agent_id: Optional[str] = None) -> str:
    """List deals with optional filters."""
    out = [
        model_dict(d)
        for d in deals_db
        if (not stage or d.stage == stage) and (not agent_id or d.agent_id == agent_id)
    ]
    return dump({"count": len(out), "deals": out})


@mcp.tool()
def crm_update_deal_stage(deal_id: str, stage: str, probability: Optional[int] = None) -> str:
    """Move a deal to a new pipeline stage."""
    d = _find_deal(deal_id)
    if not d:
        return dump({"error": f"Deal not found: {deal_id}"})
    if stage not in DEAL_STAGES:
        return dump({"error": f"stage must be one of {DEAL_STAGES}"})
    d.stage = stage
    if probability is not None:
        d.probability = probability
    elif stage == "closed_won":
        d.probability = 100
    elif stage == "closed_lost":
        d.probability = 0
    d.updated_at = datetime.now()
    return dump_model(d)


@mcp.tool()
def crm_pipeline_summary() -> str:
    """Aggregate the deal pipeline by stage (count, value, weighted value)."""
    by_stage: Dict[str, Dict[str, Any]] = {}
    for d in deals_db:
        entry = by_stage.setdefault(d.stage, {"count": 0, "value": 0.0, "weighted": 0.0})
        entry["count"] += 1
        entry["value"] = round(entry["value"] + d.amount, 2)
        entry["weighted"] = round(entry["weighted"] + d.amount * d.probability / 100, 2)
    open_value = sum(e["value"] for s, e in by_stage.items() if not s.startswith("closed"))
    won_value = by_stage.get("closed_won", {}).get("value", 0.0)
    return dump(
        {
            "stages": by_stage,
            "open_pipeline_value": round(open_value, 2),
            "won_value": round(won_value, 2),
            "total_deals": len(deals_db),
        }
    )


# ---- Tasks ----


@mcp.tool()
def crm_add_task(
    title: str,
    description: Optional[str] = None,
    assigned_agent_id: Optional[str] = None,
    related_type: Optional[str] = None,
    related_id: Optional[str] = None,
    due_date: Optional[str] = None,
    priority: str = "medium",
) -> str:
    """Create a CRM task/follow-up."""
    if priority not in TASK_PRIORITIES:
        return dump({"error": f"priority must be one of {TASK_PRIORITIES}"})
    t = Task(
        title=title,
        description=description,
        assigned_agent_id=assigned_agent_id,
        related_type=related_type,
        related_id=related_id,
        due_date=due_date,
        priority=priority,
    )
    tasks_db.append(t)
    return dump_model(t)


@mcp.tool()
def crm_list_tasks(status: Optional[str] = None, agent_id: Optional[str] = None) -> str:
    """List tasks with optional filters."""
    out = [
        model_dict(t)
        for t in tasks_db
        if (not status or t.status == status) and (not agent_id or t.assigned_agent_id == agent_id)
    ]
    return dump({"count": len(out), "tasks": out})


@mcp.tool()
def crm_complete_task(task_id: str, status: str = "done") -> str:
    """Mark a task as done/in_progress/cancelled."""
    t = next((x for x in tasks_db if x.id == task_id), None)
    if not t:
        return dump({"error": f"Task not found: {task_id}"})
    if status not in TASK_STATUSES:
        return dump({"error": f"status must be one of {TASK_STATUSES}"})
    t.status = status
    t.updated_at = datetime.now()
    return dump_model(t)


# ---- Appointments ----


@mcp.tool()
def crm_schedule_appointment(
    title: str,
    scheduled_at: str,
    lead_id: Optional[str] = None,
    customer_id: Optional[str] = None,
    property_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    notes: Optional[str] = None,
) -> str:
    """Schedule a site visit / appointment."""
    a = Appointment(
        title=title,
        scheduled_at=scheduled_at,
        lead_id=lead_id,
        customer_id=customer_id,
        property_id=property_id,
        agent_id=agent_id,
        notes=notes,
    )
    appointments_db.append(a)
    return dump_model(a)


@mcp.tool()
def crm_list_appointments(status: Optional[str] = None) -> str:
    """List appointments, optionally filtered by status."""
    out = [model_dict(a) for a in appointments_db if not status or a.status == status]
    return dump({"count": len(out), "appointments": out})


@mcp.tool()
def crm_dashboard() -> str:
    """High-level CRM dashboard: leads, deals, tasks and appointments at a glance."""
    leads_by_status: Dict[str, int] = {}
    for l in leads_db:
        leads_by_status[l.status] = leads_by_status.get(l.status, 0) + 1
    open_tasks = [t for t in tasks_db if t.status in ("open", "in_progress")]
    return dump(
        {
            "agents": len(agents_db),
            "leads": {"total": len(leads_db), "by_status": leads_by_status},
            "customers": len(customers_db),
            "deals": {
                "total": len(deals_db),
                "open_value": round(
                    sum(d.amount for d in deals_db if not d.stage.startswith("closed")), 2
                ),
                "won_value": round(
                    sum(d.amount for d in deals_db if d.stage == "closed_won"), 2
                ),
            },
            "tasks": {"total": len(tasks_db), "open": len(open_tasks)},
            "appointments": len(appointments_db),
            "properties": len(properties_db),
        }
    )


# ---------- System ----------


@mcp.tool()
def server_info() -> str:
    """Server metadata: version, capability counts and the data model."""
    return dump(
        {
            "name": "RealEstatePortal",
            "version": SERVER_VERSION,
            "counts": {
                "cities": len(cities_db),
                "schemes": len(housing_schemes_db),
                "blocks": len(block_zone_areas_db),
                "properties": len(properties_db),
                "big_projects": len(big_projects_db),
                "agents": len(agents_db),
                "leads": len(leads_db),
                "customers": len(customers_db),
                "deals": len(deals_db),
                "tasks": len(tasks_db),
                "appointments": len(appointments_db),
            },
            "features": [
                "hierarchy",
                "gis",
                "memory",
                "rag",
                "big_projects",
                "images",
                "crm",
                "fastapi",
            ],
        }
    )


@mcp.tool()
def health_check() -> str:
    """Liveness probe."""
    return dump({"status": "ok", "version": SERVER_VERSION, "time": datetime.now().isoformat()})


@mcp.tool()
def fastapi_info() -> str:
    """Describe the FastAPI integration layer and its REST endpoints."""
    return dump(
        {
            "note": "The REST layer shares this module's data stores (no duplication).",
            "run": "uv run python main.py   ->  http://127.0.0.1:8000/docs",
            "mounts_mcp_at": "/mcp (Streamable HTTP)",
            "openai_compatible": {
                "base": "/v1",
                "endpoints": ["GET /v1/models", "POST /v1/chat/completions", "POST /v1/completions", "POST /v1/embeddings"],
                "mode": "proxy if PORTAL_LLM_BASE_URL is set, else local RAG fallback",
            },
            "endpoints": [
                "GET  /health",
                "GET  /properties",
                "GET  /properties/{property_id}",
                "POST /properties",
                "PUT  /properties/{property_id}",
                "DELETE /properties/{property_id}",
                "GET  /search",
                "GET  /nearby",
                "GET  /properties/{property_id}/compare/{other_id}",
                "GET  /cities",
                "GET  /schemes",
                "GET  /bigprojects",
                "GET  /rag/search",
                "GET  /memory",
                "POST /memory",
                "GET  /units/convert",
                "GET  /gis/base-maps",
                "GET  /gis/base-maps/{base_map_id}",
                "GET  /gis/layers",
                "POST /gis/layers",
                "GET  /gis/layers/{layer_id}",
                "PUT  /gis/layers/{layer_id}",
                "DELETE /gis/layers/{layer_id}",
                "GET  /gis/master-plans",
                "POST /gis/master-plans",
                "GET  /gis/properties-in-bounds",
                "POST /gis/properties-in-polygon",
                "GET  /gis/area",
                "GET  /gis/centroid",
                "GET  /gis/bearing",
                "GET  /gis/distance-matrix",
                "GET  /gis/export/geojson/{entity_type}/{entity_id}",
                "GET  /gis/export/kml/{entity_type}/{entity_id}",
                "GET  /gis/map/{entity_type}/{entity_id}",
                "GET  /gis/map",
                "GET  /gis/analysis/assumptions",
                "GET  /gis/analysis/{entity_type}/{entity_id}",
                "GET  /gis/analysis/{entity_type}/{entity_id}/cost",
                "GET  /gis/analysis/{entity_type}/{entity_id}/population",
                "GET  /gis/analysis/{entity_type}/{entity_id}/economic-impact",
                "POST /gis/buffer",
                "GET  /gis/buffer/point",
                "POST /gis/buffers",
                "GET  /gis/ring-analysis",
                "POST /gis/polygon-analysis",
                "GET  /gis/features/{scope_type}/{scope_id}",
                "GET  /gis/thematic/{scope_type}/{scope_id}",
                "GET  /gis/report/{entity_type}/{entity_id}",
                "GET  /gis/analysis/{entity_type}/{entity_id}/cost-development",
                "GET  /gis/analysis/{entity_type}/{entity_id}/factors",
                "GET  /gis/analysis/{entity_type}/{entity_id}/forecast",
                "GET  /gis/analysis/{entity_type}/{entity_id}/scenarios",
                "GET  /gis/outlook/{entity_type}/{entity_id}",
                "GET  /news",
                "POST /news",
                "GET  /news/channels",
                "GET  /news/impact",
                "GET  /news/ticker",
                "GET  /news/ticker.html",
                "GET  /crm/dashboard",
                "GET  /crm/agents",
                "GET  /crm/leads",
                "POST /crm/leads",
                "GET  /crm/customers",
                "GET  /crm/deals",
                "POST /crm/deals",
                "GET  /crm/pipeline",
                "GET  /crm/tasks",
                "POST /crm/tasks",
                "GET  /crm/appointments",
                "POST /auth/signup",
                "POST /auth/verify-otp",
                "POST /auth/resend-otp",
                "POST /auth/login",
                "POST /auth/otp/request",
                "POST /auth/otp/verify",
                "POST /auth/password/reset-request",
                "POST /auth/password/reset",
                "POST /auth/password/set",
                "GET  /auth/me",
                "POST /auth/logout",
                "POST /auth/refresh",
                "GET  /auth/users",
                "GET  /auth/otps",
                "GET  /auth/notifications",
                "GET  /auth/events",
                "GET  /auth/config",
                "GET  /i18n/languages",
                "GET  /i18n/strings/{lang}",
                "GET  /ui/themes",
                "GET  /ui/strings/{lang}",
                "--- accounting ---",
                "GET  /accounting/info",
                "GET  /accounting/accounts",
                "POST /accounting/accounts",
                "PUT  /accounting/accounts/{code}",
                "GET  /accounting/accounts/{code}/balance",
                "GET  /accounting/chart",
                "POST /accounting/journal",
                "GET  /accounting/journal",
                "GET  /accounting/journal/{entry_id}",
                "POST /accounting/journal/{entry_id}/void",
                "GET  /accounting/trial-balance",
                "GET  /accounting/ledger/{account_code}",
                "GET  /accounting/profit-and-loss",
                "GET  /accounting/balance-sheet",
                "GET  /accounting/cash-flow",
                "GET  /accounting/ratios",
                "GET  /accounting/dashboard",
                "POST /accounting/invoices",
                "GET  /accounting/invoices",
                "GET  /accounting/invoices/{invoice_id}",
                "POST /accounting/invoices/{invoice_id}/post",
                "POST /accounting/payments",
                "POST /accounting/expenses",
                "GET  /accounting/aging",
                "POST /accounting/leases",
                "GET  /accounting/leases",
                "GET  /accounting/rent-roll",
                "POST /accounting/rent-invoices",
                "POST /accounting/budgets",
                "GET  /accounting/budgets",
                "GET  /accounting/budgets/{budget_id}/variance",
                "GET  /accounting/properties/{property_id}/performance",
                "--- finance / roi ---",
                "GET  /finance/mortgage",
                "POST /finance/investment-metrics",
                "GET  /finance/cap-rate",
                "GET  /finance/cash-on-cash",
                "POST /finance/roi",
                "POST /finance/property-roi",
                "GET  /finance/rental-yield/{property_id}",
                "GET  /finance/portfolio-roi",
                "--- poi ---",
                "POST /poi",
                "GET  /poi",
                "GET  /poi/categories",
                "GET  /poi/nearby",
                "GET  /poi/nearest",
                "GET  /poi/density/{entity_type}/{entity_id}",
                "GET  /poi/accessibility",
                "GET  /poi/map",
                "POST /poi/within-polygon",
                "GET  /poi/{poi_id}",
                "PUT  /poi/{poi_id}",
                "DELETE /poi/{poi_id}",
                "--- aoi ---",
                "POST /aoi",
                "GET  /aoi",
                "POST /aoi/compare",
                "GET  /aoi/{aoi_id}",
                "PUT  /aoi/{aoi_id}",
                "DELETE /aoi/{aoi_id}",
                "GET  /aoi/{aoi_id}/stats",
                "GET  /aoi/{aoi_id}/analyze",
                "GET  /aoi/{aoi_id}/watch",
                "GET  /aoi/{aoi_id}/report",
                "GET  /aoi/{aoi_id}/map",
                "--- routing ---",
                "GET  /gis/travel-modes",
                "GET  /gis/road-classes",
                "GET  /gis/road-networks",
                "POST /gis/road-networks",
                "GET  /gis/route",
                "GET  /gis/route/compare",
                "POST /gis/route/matrix",
                "GET  /gis/route/map",
                "GET  /poi/route",
                "--- content ---",
                "GET  /content/overview",
                "GET  /content/pages",
                "POST /content/pages",
                "GET  /content/pages/{key}",
                "PUT  /content/pages/{key}",
                "DELETE /content/pages/{key}",
                "GET  /content/history",
                "POST /content/history",
                "GET  /content/contacts",
                "POST /content/contacts",
                "GET  /content/stories",
                "POST /content/stories",
                "GET  /content/navigation",
                "GET  /content/site",
                "GET  /portal/home",
                "GET  /portal/home.html",
                "--- advertising ---",
                "GET  /ads/categories",
                "GET  /ads/slots",
                "POST /ads",
                "GET  /ads",
                "GET  /ads/active",
                "GET  /ads/performance",
                "GET  /ads/section",
                "GET  /ads/preview",
                "GET  /ads/report",
                "GET  /ads/{ad_id}",
                "PUT  /ads/{ad_id}",
                "DELETE /ads/{ad_id}",
                "POST /ads/{ad_id}/track",
                "--- users & roles ---",
                "GET  /roles",
                "POST /roles",
                "GET  /roles/permissions",
                "GET  /roles/summary",
                "GET  /roles/{name}",
                "PUT  /roles/{name}",
                "DELETE /roles/{name}",
                "GET  /roles/{name}/users",
                "GET  /users/{user_id}/roles",
                "PUT  /users/{user_id}/roles",
                "POST /users/{user_id}/roles",
                "DELETE /users/{user_id}/roles/{role}",
                "GET  /users/{user_id}/permissions",
                "POST /users/{user_id}/permissions",
                "DELETE /users/{user_id}/permissions/{permission}",
                "GET  /users/{user_id}/permissions/check",
                "--- portal ---",
                "GET  /portal/health",
                "GET  /portal/catalog",
                "GET  /portal/schema",
                "GET  /portal/settings",
                "PUT  /portal/settings",
                "GET  /portal/audit",
                "GET  /portal/search",
                "GET  /portal/statistics",
                "GET  /portal/availability",
                "GET  /portal/market-trends",
                "--- construction ---",
                "GET  /construction/overview",
                "GET  /construction/techniques",
                "GET  /construction/techniques/{key}",
                "GET  /construction/materials",
                "GET  /construction/materials/{key}",
                "GET  /construction/element-rates",
                "GET  /construction/rate-analysis",
                "POST /construction/estimate",
                "GET  /construction/timeline",
                "GET  /construction/takeoff",
                "GET  /construction/compare",
                "GET  /construction/impact",
                "GET  /construction/advisory",
                "GET  /construction/guidelines",
                "GET  /construction/approvals",
                "GET  /construction/qa",
                "GET  /construction/hse",
                "GET  /construction/trades",
                "POST /construction/estimates",
                "GET  /construction/estimates",
                "GET  /construction/estimates/{estimate_id}",
                "GET  /construction/portal",
                "GET  /construction/portal.html",
                "POST /construction/report",
                "--- maintenance ---",
                "GET  /maintenance/overview",
                "GET  /maintenance/components",
                "GET  /maintenance/components/{key}",
                "GET  /maintenance/services",
                "GET  /maintenance/services/{key}",
                "GET  /maintenance/defects",
                "GET  /maintenance/defects/{key}",
                "GET  /maintenance/estimate",
                "GET  /maintenance/schedule",
                "GET  /maintenance/lifecycle",
                "GET  /maintenance/reserve",
                "GET  /maintenance/condition",
                "GET  /maintenance/repair-estimate",
                "GET  /maintenance/repair-or-replace",
                "GET  /maintenance/impact",
                "GET  /maintenance/guidelines",
                "GET  /maintenance/warranty",
                "GET  /maintenance/inspection",
                "POST /maintenance/plans",
                "GET  /maintenance/plans",
                "GET  /maintenance/plans/{plan_id}",
                "POST /maintenance/work-orders",
                "GET  /maintenance/work-orders",
                "GET  /maintenance/work-orders/{wo_id}",
                "PUT  /maintenance/work-orders/{wo_id}",
                "GET  /maintenance/portal",
                "GET  /maintenance/portal.html",
                "POST /maintenance/report",
                "--- agentic os ---",
                "GET  /agents/overview",
                "GET  /agents/catalog",
                "GET  /agents/products",
                "GET  /agents/{key}",
                "POST /agents/plan",
                "POST /agents/run",
                "GET  /agents/runs",
                "GET  /agents/runs/{run_id}",
                "POST /agents/runs/{run_id}/approve",
                "GET  /agents/smart-actions",
                "GET  /agents/move-likelihood/{lead_id}",
                "GET  /agents/seller-intent",
                "POST /agents/orchestrate",
                "GET  /agents/portal",
                "GET  /agents/portal.html",
                "--- transactions ---",
                "GET  /transactions/stages",
                "POST /transactions",
                "GET  /transactions",
                "GET  /transactions/{tx_id}",
                "PUT  /transactions/{tx_id}",
                "POST /transactions/{tx_id}/milestones",
                "POST /transactions/{tx_id}/milestones/{key}/complete",
                "POST /transactions/terms/extract",
                "POST /transactions/{tx_id}/offers",
                "POST /transactions/offers/{offer_id}/respond",
                "POST /transactions/{tx_id}/signatures",
                "GET  /transactions/{tx_id}/signatures",
                "GET  /transactions/{tx_id}/progress",
                "GET  /transactions/deadlines",
                "POST /transactions/{tx_id}/close",
                "POST /transactions/{tx_id}/report",
                "--- intelligence (buyer / seller / investor) ---",
                "POST /intelligence/buyer/parse",
                "POST /intelligence/buyer/recommend",
                "GET  /intelligence/buyer/anomalies",
                "GET  /intelligence/buyer/affordability",
                "POST /intelligence/buyer/report",
                "GET  /intelligence/seller/cma/{property_id}",
                "GET  /intelligence/seller/net-proceeds",
                "GET  /intelligence/seller/marketing/{property_id}",
                "POST /intelligence/seller/report/{property_id}",
                "POST /intelligence/investment/underwrite",
                "GET  /intelligence/investment/screen",
                "POST /intelligence/investment/alerts",
                "POST /intelligence/investment/report",
                "--- leasing ---",
                "GET  /leasing/units",
                "POST /leasing/units",
                "GET  /leasing/units/{unit_id}",
                "GET  /leasing/rent-floor",
                "POST /leasing/inquiries",
                "GET  /leasing/inquiries",
                "POST /leasing/apply",
                "GET  /leasing/renewals",
                "GET  /leasing/collection",
                "GET  /leasing/funnel",
                "GET  /leasing/portal",
                "GET  /leasing/portal.html",
                "--- marketing ---",
                "GET  /marketing/channels",
                "GET  /marketing/routes",
                "POST /marketing/routes",
                "POST /marketing/qualify/{lead_id}",
                "POST /marketing/route/{lead_id}",
                "GET  /marketing/reengagement",
                "POST /marketing/content",
                "GET  /marketing/content",
                "POST /marketing/content/{asset_id}/approve",
                "POST /marketing/campaigns",
                "GET  /marketing/funnel",
                "GET  /marketing/portal",
                "GET  /marketing/portal.html",
                "--- commercialization ---",
                "GET  /commercial/products",
                "GET  /commercial/products/{key}",
                "GET  /commercial/plans",
                "GET  /commercial/plans/{key}",
                "GET  /commercial/pricing",
                "POST /commercial/recommend",
                "POST /commercial/subscribe",
                "GET  /commercial/subscriptions",
                "POST /commercial/meter",
                "GET  /commercial/usage/{account}",
                "GET  /commercial/bill/{account}",
                "POST /commercial/revenue-share",
                "POST /commercial/payouts",
                "GET  /commercial/payouts",
                "GET  /commercial/gtm",
                "GET  /commercial/portal",
                "GET  /commercial/portal.html",
                "--- product surfaces (mcp-for-brokers / property intelligence) ---",
                "GET  /broker/contacts",
                "GET  /broker/commission-projection",
                "GET  /broker/property-gis",
                "GET  /broker/listing-draft/{property_id}",
                "GET  /property-intelligence/gis-score",
                "GET  /property-intelligence/accounting-snapshot/{property_id}",
                "GET  /property-intelligence/market-intelligence",
                "GET  /property-intelligence/seller-intent/{contact_id}",
                "--- tools & utilities ---",
                "GET  /tools/overview",
                "GET  /tools/categories",
                "GET  /tools/catalog",
                "GET  /tools/catalog/{key}",
                "GET  /tools/area-units",
                "GET  /tools/convert/area",
                "GET  /tools/convert/area-table",
                "GET  /tools/convert/length",
                "GET  /tools/plot/dimensions",
                "GET  /tools/plot/studio",
                "GET  /tools/plot/diagram",
                "GET  /tools/calculators",
                "POST /tools/calculators/mortgage",
                "POST /tools/calculators/installment",
                "POST /tools/calculators/rental-yield",
                "POST /tools/calculators/appreciation",
                "POST /tools/calculators/price-per-unit",
                "POST /tools/calculators/transfer-costs",
                "POST /tools/calculators/commission",
                "POST /tools/calculators/capital-gains",
                "POST /tools/calculators/joint-investment",
                "POST /tools/calculators/rent-vs-buy",
                "POST /tools/calculators/construction-cost",
                "POST /tools/calculators/material-quantities",
                "POST /tools/calculators/build-timeline",
                "GET  /tools/gis/crs",
                "POST /tools/gis/measure",
                "POST /tools/gis/polygon-area",
                "POST /tools/gis/georeference",
                "POST /tools/gis/transform",
                "POST /tools/gis/aerial-compare",
                "POST /tools/gis/export",
                "POST /tools/gis/import",
                "POST /tools/gis/nearby",
                "GET  /tools/cad/formats",
                "POST /tools/cad/inspect",
                "POST /tools/cad/dxf-preview",
                "POST /tools/cad/compare-revisions",
                "POST /tools/cad/layout-sheet",
                "POST /tools/photo/read-gps",
                "POST /tools/photo/write-gps",
                "POST /tools/photo/geotag-batch",
                "POST /tools/photo/report",
                "GET  /tools/photo/privacy-check",
                "GET  /tools/documents/tools",
                "GET  /tools/documents/convert-guide",
                "POST /tools/documents/text-to-pdf",
                "POST /tools/documents/images-to-pdf",
                "POST /tools/documents/brochure",
                "POST /tools/documents/pdf-info",
                "GET  /tools/documents/resize-plan",
                "GET  /tools/calendar/hijri",
                "GET  /tools/calendar/gregorian",
                "GET  /tools/calendar/occasions",
                "GET  /tools/calendar/holidays",
                "POST /tools/calendar/ics",
                "POST /tools/calendar/reminders",
                "POST /tools/calendar/milestones",
                "POST /tools/calendar/possession",
                "POST /tools/reports/comparison",
                "POST /tools/reports/investment-summary",
                "POST /tools/reports/plot-inventory",
                "POST /tools/reports/csv",
                "POST /tools/reports/markdown",
                "GET  /tools/projects",
                "POST /tools/projects",
                "GET  /tools/projects/{project_id}",
                "DELETE /tools/projects/{project_id}",
                "GET  /tools/portal",
                "GET  /tools/portal.html",
                "--- pmo (project management) ---",
                "GET  /pmo/overview",
                "GET  /pmo/capabilities",
                "GET  /pmo/project-types",
                "GET  /pmo/phase-templates",
                "GET  /pmo/projects",
                "POST /pmo/projects",
                "GET  /pmo/projects/{project_id}",
                "PUT  /pmo/projects/{project_id}",
                "DELETE /pmo/projects/{project_id}",
                "GET  /pmo/projects/{project_id}/dashboard",
                "GET  /pmo/projects/{project_id}/report",
                "GET  /pmo/projects/{project_id}/phases",
                "POST /pmo/projects/{project_id}/phases",
                "GET  /pmo/projects/{project_id}/milestones",
                "POST /pmo/projects/{project_id}/milestones",
                "GET  /pmo/projects/{project_id}/tasks",
                "POST /pmo/projects/{project_id}/tasks",
                "GET  /pmo/projects/{project_id}/schedule",
                "GET  /pmo/projects/{project_id}/critical-path",
                "GET  /pmo/projects/{project_id}/gantt",
                "GET  /pmo/projects/{project_id}/costs",
                "POST /pmo/projects/{project_id}/costs",
                "GET  /pmo/projects/{project_id}/progress",
                "POST /pmo/projects/{project_id}/progress",
                "GET  /pmo/projects/{project_id}/earned-value",
                "GET  /pmo/projects/{project_id}/cost-status",
                "GET  /pmo/projects/{project_id}/s-curve",
                "GET  /pmo/projects/{project_id}/health",
                "GET  /pmo/projects/{project_id}/kpi",
                "GET  /pmo/projects/{project_id}/monitoring",
                "GET  /pmo/projects/{project_id}/risks",
                "POST /pmo/projects/{project_id}/risks",
                "GET  /pmo/projects/{project_id}/risk-matrix",
                "GET  /pmo/projects/{project_id}/site-logs",
                "POST /pmo/projects/{project_id}/site-logs",
                "GET  /pmo/projects/{project_id}/site-report",
                "GET  /pmo/projects/{project_id}/changes",
                "POST /pmo/projects/{project_id}/changes",
                "GET  /pmo/projects/{project_id}/inspections",
                "POST /pmo/projects/{project_id}/inspections",
                "GET  /pmo/projects/{project_id}/actions",
                "POST /pmo/projects/{project_id}/actions",
                "POST /pmo/projects/{project_id}/apply-template",
                "POST /pmo/from-estimate/{estimate_id}",
                "GET  /pmo/tasks/{task_id}",
                "PUT  /pmo/tasks/{task_id}",
                "DELETE /pmo/tasks/{task_id}",
                "GET  /pmo/resources",
                "POST /pmo/resources",
                "POST /pmo/allocations",
                "GET  /pmo/resource-load",
                "GET  /pmo/alerts",
                "GET  /pmo/portfolio",
                "GET  /pmo/risks",
                "PUT  /pmo/risks/{risk_id}",
                "GET  /pmo/changes/{change_id}/decide",
                "POST /pmo/changes/{change_id}/decide",
                "GET  /pmo/actions",
                "POST /pmo/actions/{action_id}/close",
                "GET  /pmo/report.html",
                "GET  /pmo/portal",
                "GET  /pmo/portal.html",
                "--- messaging (team communication & notifications) ---",
                "GET  /messaging/overview",
                "GET  /messaging/channels",
                "GET  /messaging/categories",
                "GET  /messaging/attachment-kinds",
                "GET  /messaging/profiles",
                "POST /messaging/presence",
                "POST /messaging/presence/heartbeat",
                "GET  /messaging/preferences/{user_id}",
                "PUT  /messaging/preferences/{user_id}",
                "GET  /messaging/conversations",
                "POST /messaging/conversations",
                "GET  /messaging/conversations/{conversation_id}",
                "GET  /messaging/conversations/{conversation_id}/context",
                "POST /messaging/conversations/{conversation_id}/archive",
                "GET  /messaging/conversations/{conversation_id}/members",
                "POST /messaging/conversations/{conversation_id}/members",
                "PUT  /messaging/conversations/{conversation_id}/members/{member_id}",
                "DELETE /messaging/conversations/{conversation_id}/members/{member_id}",
                "POST /messaging/direct",
                "POST /messaging/property-thread",
                "POST /messaging/revoke-access",
                "GET  /messaging/conversations/{conversation_id}/messages",
                "POST /messaging/conversations/{conversation_id}/messages",
                "GET  /messaging/conversations/{conversation_id}/read",
                "GET  /messaging/conversations/{conversation_id}/summary",
                "GET  /messaging/conversations/{conversation_id}/digest",
                "POST /messaging/conversations/{conversation_id}/action-items",
                "GET  /messaging/conversations/{conversation_id}/attachments",
                "POST /messaging/conversations/{conversation_id}/attachments",
                "GET  /messaging/conversations/{conversation_id}/actions",
                "POST /messaging/conversations/{conversation_id}/actions",
                "GET  /messaging/messages/{message_id}",
                "PUT  /messaging/messages/{message_id}",
                "DELETE /messaging/messages/{message_id}",
                "POST /messaging/messages/{message_id}/pin",
                "POST /messaging/messages/{message_id}/react",
                "GET  /messaging/messages/{message_id}/thread",
                "GET  /messaging/messages/{message_id}/receipts",
                "GET  /messaging/search",
                "GET  /messaging/unread/{user_id}",
                "GET  /messaging/unread-summary/{user_id}",
                "GET  /messaging/attachments/{attachment_id}/link",
                "GET  /messaging/attachments/{attachment_id}",
                "GET  /messaging/attachments/resolve/{token}",
                "GET  /messaging/actions",
                "GET  /messaging/actions/{action_id}",
                "PUT  /messaging/actions/{action_id}",
                "POST /messaging/actions/{action_id}/complete",
                "GET  /messaging/notifications/{user_id}",
                "POST /messaging/notifications/{notification_id}/read",
                "POST /messaging/notifications/{user_id}/read-all",
                "POST /messaging/dispatch",
                "GET  /messaging/outbox",
                "POST /messaging/telegram/link-code",
                "POST /messaging/telegram/link",
                "POST /messaging/telegram/unlink",
                "GET  /messaging/telegram/links",
                "GET  /messaging/telegram/status/{user_id}",
                "POST /messaging/telegram/update",
                "POST /messaging/telegram/alert",
                "GET  /messaging/audit",
                "GET  /messaging/retention",
                "POST /messaging/purge",
                "GET  /messaging/reports",
                "POST /messaging/reports",
                "POST /messaging/reports/{report_id}/moderate",
                "GET  /messaging/statistics",
                "GET  /messaging/portal",
                "GET  /messaging/portal.html",
                "WS   /ws/messaging/{conversation_id}",
            ],
        }
    )


# ============================================================
# ==================== MCP RESOURCES =========================
# ============================================================


@mcp.resource("cities://all", name="All cities", description="Every city with coordinates and counts.")
def res_cities() -> str:
    return list_cities()


@mcp.resource("city://{city_id}", name="City", description="A single city by id or name.")
def res_city(city_id: str) -> str:
    return get_city_details(city_id)


@mcp.resource("schemes://all", name="All schemes", description="Every housing scheme.")
def res_schemes() -> str:
    return list_schemes()


@mcp.resource("blocks://all", name="All blocks", description="Every block/zone/area.")
def res_blocks() -> str:
    return list_blocks()


@mcp.resource("properties://all", name="All properties", description="Every property (compact).")
def res_properties() -> str:
    out = []
    for p in properties_db:
        out.append(
            {
                "id": p.id,
                "title": p.title,
                "price": p.price,
                "city": city_name(p.city_id),
                "use_type": p.use_type,
                "category": p.category,
                "marla": p.marla_area,
            }
        )
    return dump({"count": len(out), "properties": out})


@mcp.resource("property://{property_id}", name="Property", description="One property by id.")
def res_property(property_id: str) -> str:
    return get_property_by_id(property_id)


@mcp.resource("properties://compare/{property_ids}", name="Compare properties", description="Compare properties by comma-separated ids.")
def res_compare(property_ids: str) -> str:
    ids = [x.strip() for x in property_ids.split(",") if x.strip()]
    items = []
    for pid in ids:
        p = find_property(pid)
        if p:
            d = model_dict(p)
            d["price_per_sqft"] = round(p.price / p.total_area, 2) if p.total_area else None
            items.append(d)
    return dump({"count": len(items), "properties": items})


@mcp.resource("gis://city/{city_id}", name="City GIS", description="Coordinates of a city.")
def res_gis_city(city_id: str) -> str:
    return get_city_coordinates(city_id)


@mcp.resource("gis://nearby/{latitude}/{longitude}/{radius_km}", name="Nearby", description="Nearby properties around a point.")
def res_gis_nearby(latitude: str, longitude: str, radius_km: str) -> str:
    return search_nearby_properties(float(latitude), float(longitude), float(radius_km))


@mcp.resource("gis://basemaps", name="Base maps", description="Available base maps (Google Earth-style imagery + open alternatives).")
def res_gis_basemaps() -> str:
    return gis_list_base_maps()


@mcp.resource("gis://layers/{entity_type}/{entity_id}", name="Entity layers", description="GIS layers attached to an entity.")
def res_gis_layers(entity_type: str, entity_id: str) -> str:
    return gis_list_layers(entity_type, entity_id)


@mcp.resource("gis://masterplans/{entity_type}/{entity_id}", name="Entity master plans", description="Master plan / zone / layout layers of an entity.")
def res_gis_masterplans(entity_type: str, entity_id: str) -> str:
    return gis_list_master_plans(entity_type, entity_id)


@mcp.resource("gis://geojson/{entity_type}/{entity_id}", name="Entity GeoJSON", description="Properties + layers of an entity as GeoJSON.")
def res_gis_geojson(entity_type: str, entity_id: str) -> str:
    return gis_export_geojson(entity_type, entity_id)


@mcp.resource("gis://kml/{entity_type}/{entity_id}", name="Entity KML", description="KML export of an entity for Google Earth.")
def res_gis_kml(entity_type: str, entity_id: str) -> str:
    return gis_export_kml(entity_type, entity_id)


@mcp.resource("gis://map/{entity_type}/{entity_id}", name="Entity map", description="Interactive Leaflet map (HTML) of an entity.")
def res_gis_map(entity_type: str, entity_id: str) -> str:
    return gis_map_preview(entity_type, entity_id)


@mcp.resource("gis://analysis/assumptions", name="Analytics assumptions", description="Planning assumptions for cost / population / economic estimates.")
def res_gis_assumptions() -> str:
    return gis_analysis_assumptions()


@mcp.resource("gis://analysis/{entity_type}/{entity_id}", name="Area analysis", description="Area, valuation, population, cost and economic analysis of an entity.")
def res_gis_analysis(entity_type: str, entity_id: str) -> str:
    return gis_area_analysis(entity_type, entity_id)


@mcp.resource("gis://report/{entity_type}/{entity_id}", name="Area report", description="Printable HTML analysis report of an entity.")
def res_gis_report(entity_type: str, entity_id: str) -> str:
    return gis_area_report(entity_type, entity_id)


@mcp.resource("gis://cost/{entity_type}/{entity_id}", name="Cost & development", description="Cost & development analysis (GDV, margin, ROI, break-even).")
def res_gis_cost(entity_type: str, entity_id: str) -> str:
    return gis_cost_development_analysis(entity_type, entity_id)


@mcp.resource("gis://forecast/{entity_type}/{entity_id}", name="Forecast", description="Multi-factor future predictions and scenarios for an entity.")
def res_gis_forecast(entity_type: str, entity_id: str) -> str:
    return gis_forecast(entity_type, entity_id)


@mcp.resource("gis://outlook/{entity_type}/{entity_id}", name="Outlook report", description="Printable HTML investment-outlook report with news ticker.")
def res_gis_outlook(entity_type: str, entity_id: str) -> str:
    return gis_outlook_report(entity_type, entity_id)


@mcp.resource("news://all", name="All news", description="Every news item tracked for real-estate impact.")
def res_news_all() -> str:
    return news_list(limit=100)


@mcp.resource("news://ticker", name="News ticker", description="Scrolling real-estate news ticker (HTML).")
def res_news_ticker() -> str:
    return news_ticker()


@mcp.resource("news://channels", name="News channels", description="News channels with counts and average impact.")
def res_news_channels() -> str:
    return news_channels()


@mcp.resource("news://impact", name="News impact", description="Aggregate news sentiment and its effect on the outlook.")
def res_news_impact() -> str:
    return news_impact()


@mcp.resource("images://{entity_type}/{entity_id}", name="Entity images", description="Images stored for an entity.")
def res_images(entity_type: str, entity_id: str) -> str:
    return image_list(entity_type, entity_id)


@mcp.resource("bigprojects://all", name="All big projects", description="Every big project.")
def res_bigprojects() -> str:
    return list_big_projects()


@mcp.resource("bigproject://{project_id}", name="Big project", description="One big project by id.")
def res_bigproject(project_id: str) -> str:
    return get_big_project_by_id(project_id)


@mcp.resource("bigprojects://city/{city_id}", name="Big projects in city", description="Big projects in a city.")
def res_bigprojects_city(city_id: str) -> str:
    return list_big_projects(city=city_id)


@mcp.resource("crm://agents", name="CRM agents", description="All sales agents.")
def res_crm_agents() -> str:
    return crm_list_agents()


@mcp.resource("crm://leads", name="CRM leads", description="All sales leads.")
def res_crm_leads() -> str:
    return crm_list_leads()


@mcp.resource("crm://customers", name="CRM customers", description="All customers.")
def res_crm_customers() -> str:
    return crm_list_customers()


@mcp.resource("crm://deals", name="CRM deals", description="All deals.")
def res_crm_deals() -> str:
    return crm_list_deals()


@mcp.resource("crm://pipeline", name="CRM pipeline", description="Deal pipeline summary.")
def res_crm_pipeline() -> str:
    return crm_pipeline_summary()


@mcp.resource("crm://tasks", name="CRM tasks", description="All tasks.")
def res_crm_tasks() -> str:
    return crm_list_tasks()


@mcp.resource("crm://dashboard", name="CRM dashboard", description="CRM dashboard.")
def res_crm_dashboard() -> str:
    return crm_dashboard()


# ============================================================
# ==================== MCP PROMPTS ===========================
# ============================================================


@mcp.prompt(name="property_recommendation", description="Draft a recommendation request for a buyer.")
def prompt_property_recommendation(budget: str = "any", city: str = "any", use_type: str = "residential") -> str:
    return (
        "You are a senior real-estate advisor for a Pakistani property portal.\n"
        f"Client budget: {budget}. Preferred city: {city}. Use type: {use_type}.\n"
        "Use the search_properties, rag_search and investment_analysis tools to shortlist 3 properties, "
        "explain the trade-offs and give a clear recommendation."
    )


@mcp.prompt(name="lead_followup", description="Draft a follow-up plan for a CRM lead.")
def prompt_lead_followup(lead_id: str) -> str:
    lead = _find_lead(lead_id)
    detail = dump_model(lead) if lead else f"(lead {lead_id} not found)"
    return (
        "You are a real-estate CRM assistant.\n"
        f"Lead:\n{detail}\n"
        "Summarise the lead, propose the next best action, draft a short follow-up message "
        "and suggest matching properties using crm_get_lead and search_properties."
    )


@mcp.prompt(name="investment_analysis_prompt", description="Generate an investment report for a property.")
def prompt_investment(property_id: str) -> str:
    return (
        "Act as a property investment analyst.\n"
        f"Run investment_analysis and market_insights for property {property_id} and its city, "
        "then produce a concise investment memo with risks and a buy/hold/pass verdict."
    )


# ============================================================
# ==================== AUTHENTICATION ========================
# ============================================================


@mcp.tool()
def auth_signup(
    email: Optional[str] = None,
    mobile: Optional[str] = None,
    password: Optional[str] = None,
    name: Optional[str] = None,
    role: str = "user",
) -> str:
    """Create an account with an email and/or a mobile number.

    The account is created in **pending** status and an OTP is sent to every
    identifier supplied; it only becomes active after ``auth_verify_otp``.
    """
    result = auth.signup(email=email, mobile=mobile, password=password, name=name, role=role)
    user = result.get("user")
    if user and not result.get("error"):
        customer = Customer(
            name=name or user.get("email") or user.get("mobile") or "Portal user",
            email=user.get("email"),
            phone=user.get("mobile"),
            type="buyer",
            notes="Auto-created from portal signup (pending OTP verification).",
        )
        customers_db.append(customer)
        auth.link_customer(user["id"], customer.id)
        user["customer_id"] = customer.id
    return dump(result)


@mcp.tool()
def auth_verify_otp(identifier: str, code: str, purpose: str = "signup") -> str:
    """Verify the signup/login/reset OTP. Activating a signup returns a bearer token."""
    return dump(auth.verify_otp(identifier, code, purpose=purpose))


@mcp.tool()
def auth_resend_otp(identifier: str, purpose: str = "signup") -> str:
    """Re-send a verification code (subject to a cooldown and an hourly cap)."""
    return dump(auth.resend_otp(identifier, purpose=purpose))


@mcp.tool()
def auth_login(identifier: str, password: str) -> str:
    """Password login for a verified account. Returns a bearer token."""
    return dump(auth.login(identifier, password))


@mcp.tool()
def auth_request_otp(identifier: str) -> str:
    """Start a passwordless login by sending an OTP to the email/mobile."""
    return dump(auth.request_login_otp(identifier))


@mcp.tool()
def auth_verify_login_otp(identifier: str, code: str) -> str:
    """Complete a passwordless login with the OTP; returns a bearer token."""
    return dump(auth.verify_login_otp(identifier, code))


@mcp.tool()
def auth_request_password_reset(identifier: str) -> str:
    """Send a password-reset code to the account's email/mobile."""
    return dump(auth.request_password_reset(identifier))


@mcp.tool()
def auth_reset_password(identifier: str, code: str, new_password: str) -> str:
    """Reset a password with the reset code (revokes all existing sessions)."""
    return dump(auth.reset_password(identifier, code, new_password))


@mcp.tool()
def auth_set_password(token: str, new_password: str, current_password: Optional[str] = None) -> str:
    """Set or change the password of the signed-in user."""
    return dump(auth.set_password(token, new_password, current_password))


@mcp.tool()
def auth_me(token: str) -> str:
    """Return the account behind a bearer token."""
    return dump(auth.me(token))


@mcp.tool()
def auth_logout(token: str) -> str:
    """Revoke the bearer token."""
    return dump(auth.logout(token))


@mcp.tool()
def auth_refresh(token: str) -> str:
    """Exchange a valid token for a fresh one (the old one is revoked)."""
    return dump(auth.refresh(token))


@mcp.tool()
def auth_list_users(role: Optional[str] = None, status: Optional[str] = None) -> str:
    """List accounts, optionally filtered by role and/or status."""
    users = auth.list_users(role=role, status=status)
    return dump({"count": len(users), "users": users})


@mcp.tool()
def auth_set_status(user_id: str, status: str) -> str:
    """Activate / suspend an account (suspending revokes its sessions)."""
    return dump(auth.set_status(user_id, status))


@mcp.tool()
def auth_set_role(user_id: str, role: str) -> str:
    """Change an account's role (user / agent / admin)."""
    return dump(auth.set_role(user_id, role))


@mcp.tool()
def auth_get_otp(identifier: str, purpose: str = "signup") -> str:
    """Dev helper: return the newest unconsumed OTP for an identifier.

    Codes are only exposed when ``PORTAL_AUTH_EXPOSE_OTP`` is on (default).
    """
    rows = auth.list_otps(identifier=identifier, purpose=purpose, limit=1)
    if not rows:
        return dump({"error": "No pending code for this identifier", "code": "no_otp"})
    row = rows[0]
    if not auth.AUTH_CONFIG["expose_otp"]:
        row["code"] = None
        row["note"] = "Set PORTAL_AUTH_EXPOSE_OTP=1 to expose codes outside a real channel."
    return dump(row)


@mcp.tool()
def auth_list_otps(
    identifier: Optional[str] = None, purpose: Optional[str] = None, limit: int = 25
) -> str:
    """List outstanding verification codes (plaintext only while ``PORTAL_AUTH_EXPOSE_OTP`` is on)."""
    rows = auth.list_otps(identifier=identifier, purpose=purpose, limit=limit)
    if not auth.AUTH_CONFIG["expose_otp"]:
        for row in rows:
            row["code"] = None
    return dump({"count": len(rows), "otps": rows})


@mcp.tool()
def auth_notifications(channel: Optional[str] = None, limit: int = 25) -> str:
    """The simulated SMS/e-mail outbox — every OTP that was 'sent'."""
    notes = auth.list_notifications(limit=limit, channel=channel)
    return dump({"count": len(notes), "notifications": notes})


@mcp.tool()
def auth_events(limit: int = 50) -> str:
    """Authentication audit trail (signup, login, OTP sent/failed/verified, …)."""
    events = auth.list_events(limit=limit)
    return dump({"count": len(events), "events": events})


@mcp.tool()
def auth_config() -> str:
    """OTP/session/password policy plus live counters."""
    return dump(auth.get_config())


@mcp.resource("auth://users", name="Auth users", description="All registered accounts.")
def res_auth_users() -> str:
    return auth_list_users()


@mcp.resource("auth://config", name="Auth config", description="OTP/session/password policy and counters.")
def res_auth_config() -> str:
    return auth_config()


@mcp.resource("auth://otps", name="Pending OTPs", description="Outstanding verification codes.")
def res_auth_otps() -> str:
    return auth_notifications()


@mcp.resource("auth://events", name="Auth events", description="Authentication audit trail.")
def res_auth_events() -> str:
    return auth_events()


@mcp.prompt(name="signup_flow_prompt", description="Guide an agent through the OTP signup flow.")
def prompt_signup_flow() -> str:
    return (
        "Walk a new user through registering on the portal.\n"
        "1. Collect an email and/or mobile number (Pakistani 03xx numbers are normalised to +923xx).\n"
        "2. Call auth_signup; the account stays 'pending'.\n"
        "3. Call auth_get_otp to read the code (dev), then auth_verify_otp.\n"
        "4. Store the returned bearer token and use it with auth_me for protected calls."
    )


# ============================================================
# ============ POINTS OF INTEREST (POI) ======================
# ============================================================

POI_CATEGORIES = [
    "education", "health", "shopping", "worship", "transport", "park",
    "restaurant", "bank", "fuel", "government", "hotel", "sports", "other",
]

# Relative weight of each category when scoring liveability / accessibility.
POI_CATEGORY_WEIGHTS: Dict[str, float] = {
    "education": 1.2, "health": 1.3, "transport": 1.1, "shopping": 0.9,
    "worship": 0.6, "park": 0.8, "restaurant": 0.5, "bank": 0.6,
    "fuel": 0.5, "government": 0.7, "hotel": 0.4, "sports": 0.6, "other": 0.3,
}


class PointOfInterest(BaseModel):
    """A nearby facility / landmark used for liveability and accessibility scoring."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    category: str = "other"
    subcategory: Optional[str] = None
    latitude: float
    longitude: float
    address: Optional[str] = None
    city_id: Optional[str] = None
    scheme_id: Optional[str] = None
    block_zone_area_id: Optional[str] = None
    rating: Optional[float] = None
    importance: float = 1.0  # multiplier on the category weight
    source: str = "manual"
    tags: List[str] = Field(default_factory=list)
    image_urls: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


pois_db: List[PointOfInterest] = []


# ============================================================
# ============ AREAS OF INTEREST (AOI) =======================
# ============================================================

AOI_KINDS = ["circle", "polygon", "bbox", "entity"]


class AreaOfInterest(BaseModel):
    """A saved, analysable footprint: a radius, a polygon, a bbox or an entity."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: Optional[str] = None
    kind: str = "circle"  # circle | polygon | bbox | entity

    # circle
    center_latitude: Optional[float] = None
    center_longitude: Optional[float] = None
    radius_m: Optional[float] = None

    # polygon: [[lat, lon], ...]
    coordinates: List[List[float]] = Field(default_factory=list)

    # bbox: {south, west, north, east}
    bounds: Optional[Dict[str, float]] = None

    # entity
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None

    city_id: Optional[str] = None
    scheme_id: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    watch_categories: List[str] = Field(default_factory=list)  # news categories to watch
    watch_alert_threshold: float = 0.0  # absolute impact_score that raises an alert
    created_by: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


aois_db: List[AreaOfInterest] = []


def _geom_ring(geom: Optional[Dict[str, Any]]) -> List[List[float]]:
    """Outer ring ([[lon, lat], ...]) of a Polygon / MultiPolygon geometry."""
    if not geom:
        return []
    gtype = geom.get("type")
    if gtype == "Polygon":
        return geom["coordinates"][0]
    if gtype == "MultiPolygon":
        return geom["coordinates"][0][0]
    return []


def _poi_view(poi: PointOfInterest) -> Dict[str, Any]:
    data = model_dict(poi)
    data["city_name"] = city_name(poi.city_id) if poi.city_id else None
    return data


def _poi_filter(
    category: Optional[str] = None,
    categories: Optional[List[str]] = None,
    city_id: Optional[str] = None,
    scheme_id: Optional[str] = None,
    query: Optional[str] = None,
) -> List[PointOfInterest]:
    rows = list(pois_db)
    if category:
        rows = [p for p in rows if p.category == category]
    if categories:
        rows = [p for p in rows if p.category in categories]
    if city_id:
        rows = [p for p in rows if p.city_id == city_id]
    if scheme_id:
        rows = [p for p in rows if p.scheme_id == scheme_id]
    if query:
        q = query.lower()
        rows = [
            p for p in rows
            if q in p.name.lower()
            or q in (p.subcategory or "").lower()
            or any(q in t.lower() for t in p.tags)
        ]
    return rows


def _poi_near(lat: float, lon: float, radius_m: float, **filters: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for poi in _poi_filter(**filters):
        d = gis.haversine_m(lat, lon, poi.latitude, poi.longitude)
        if d <= radius_m:
            row = _poi_view(poi)
            row["distance_m"] = round(d, 1)
            row["distance_km"] = round(d / 1000.0, 3)
            out.append(row)
    out.sort(key=lambda r: r["distance_m"])
    return out


def _poi_nearest_by_category(lat: float, lon: float, radius_m: float = 25000.0) -> List[Dict[str, Any]]:
    best: Dict[str, Dict[str, Any]] = {}
    for poi in pois_db:
        d = gis.haversine_m(lat, lon, poi.latitude, poi.longitude)
        if d > radius_m:
            continue
        cur = best.get(poi.category)
        if cur is None or d < cur["distance_m"]:
            row = _poi_view(poi)
            row["distance_m"] = round(d, 1)
            best[poi.category] = row
    return sorted(best.values(), key=lambda r: r["distance_m"])


def _poi_accessibility(lat: float, lon: float, radius_m: float = 3000.0) -> Dict[str, Any]:
    """Distance-decayed, category-weighted liveability score (0-100)."""
    by_cat: Dict[str, Dict[str, float]] = {}
    total = 0.0
    for poi in pois_db:
        d = gis.haversine_m(lat, lon, poi.latitude, poi.longitude)
        if d > radius_m:
            continue
        weight = POI_CATEGORY_WEIGHTS.get(poi.category, 0.3) * (poi.importance or 1.0)
        contribution = weight * math.exp(-d / (radius_m / 3.0))
        row = by_cat.setdefault(poi.category, {"count": 0.0, "score": 0.0, "nearest_m": d})
        row["count"] += 1
        row["score"] += contribution
        row["nearest_m"] = min(row["nearest_m"], d)
        total += contribution
    score = round(min(100.0, total / 12.0 * 100.0), 1)
    return {
        "center": {"latitude": lat, "longitude": lon},
        "radius_m": radius_m,
        "score": score,
        "band": "excellent" if score >= 75 else "good" if score >= 55 else "fair" if score >= 35 else "poor",
        "by_category": {
            k: {"count": int(v["count"]), "nearest_m": round(v["nearest_m"], 1), "score": round(v["score"], 2)}
            for k, v in sorted(by_cat.items(), key=lambda kv: -kv[1]["score"])
        },
    }


def _aoi_geometry(aoi: AreaOfInterest) -> Optional[Dict[str, Any]]:
    if aoi.kind == "circle" and aoi.center_latitude is not None and aoi.center_longitude is not None:
        return gis.circle_polygon(aoi.center_latitude, aoi.center_longitude, aoi.radius_m or 1000.0)
    if aoi.kind == "polygon" and aoi.coordinates:
        return gis.polygon_feature(aoi.coordinates)["geometry"]
    if aoi.kind == "bbox" and aoi.bounds:
        b = aoi.bounds
        pairs = gis.bbox_polygon_pairs(b["south"], b["west"], b["north"], b["east"])
        return gis.polygon_feature(pairs)["geometry"]
    if aoi.kind == "entity" and aoi.entity_type and aoi.entity_id:
        props = _entity_properties(aoi.entity_type, aoi.entity_id)
        return _entity_geometry(aoi.entity_type, aoi.entity_id, props)
    return None


def _aoi_center(aoi: AreaOfInterest) -> tuple:
    if aoi.kind == "circle" and aoi.center_latitude is not None:
        return aoi.center_latitude, aoi.center_longitude, aoi.name
    if aoi.kind == "entity" and aoi.entity_type and aoi.entity_id:
        return _entity_center(aoi.entity_type, aoi.entity_id)
    geom = _aoi_geometry(aoi)
    box = gis.geojson_bbox(geom) if geom else None
    if box:
        return (box["south"] + box["north"]) / 2, (box["west"] + box["east"]) / 2, aoi.name
    return None, None, aoi.name


def _aoi_ring(aoi: AreaOfInterest) -> List[List[float]]:
    return _geom_ring(_aoi_geometry(aoi))


def _aoi_properties(aoi: AreaOfInterest) -> List[Property]:
    if aoi.kind == "entity" and aoi.entity_type and aoi.entity_id:
        return _entity_properties(aoi.entity_type, aoi.entity_id)
    ring = _aoi_ring(aoi)
    if not ring:
        return []
    return [
        p for p in properties_db
        if p.latitude is not None and p.longitude is not None
        and gis.point_in_polygon(p.latitude, p.longitude, ring)
    ]


def _aoi_pois(aoi: AreaOfInterest) -> List[PointOfInterest]:
    ring = _aoi_ring(aoi)
    if not ring:
        return []
    return [poi for poi in pois_db if gis.point_in_polygon(poi.latitude, poi.longitude, ring)]


def _aoi_scope(aoi: AreaOfInterest) -> tuple:
    if aoi.kind == "entity" and aoi.entity_type and aoi.entity_id:
        return _scope_for_entity(aoi.entity_type, aoi.entity_id)
    if aoi.scheme_id:
        return "scheme", aoi.scheme_id
    if aoi.city_id:
        return "city", aoi.city_id
    return "national", "PK"


def _find_aoi(aoi_id: str) -> Optional[AreaOfInterest]:
    key = str(aoi_id)
    return next(
        (a for a in aois_db if a.id == key or a.name.lower() == key.lower()), None
    )


def _aoi_view(aoi: AreaOfInterest) -> Dict[str, Any]:
    data = model_dict(aoi)
    geom = _aoi_geometry(aoi)
    data["geometry"] = geom
    box = gis.geojson_bbox(geom) if geom else None
    data["bounds"] = box
    data["area_sqm"] = round(_geometry_area_sqm(geom), 2) if geom else 0.0
    data["city_name"] = city_name(aoi.city_id) if aoi.city_id else None
    return data


@mcp.tool()
def poi_add(
    name: str,
    latitude: float,
    longitude: float,
    category: str = "other",
    subcategory: Optional[str] = None,
    address: Optional[str] = None,
    city_id: Optional[str] = None,
    scheme_id: Optional[str] = None,
    block_zone_area_id: Optional[str] = None,
    rating: Optional[float] = None,
    importance: float = 1.0,
    tags: Optional[List[str]] = None,
    source: str = "manual",
) -> str:
    """Register a point of interest (school, hospital, mall, mosque, stop, park …)."""
    if category not in POI_CATEGORIES:
        return dump({"error": f"category must be one of {POI_CATEGORIES}"})
    poi = PointOfInterest(
        name=name, latitude=latitude, longitude=longitude, category=category, subcategory=subcategory,
        address=address, city_id=city_id, scheme_id=scheme_id, block_zone_area_id=block_zone_area_id,
        rating=rating, importance=importance, tags=tags or [], source=source,
    )
    pois_db.append(poi)
    return dump(_poi_view(poi))


@mcp.tool()
def poi_list(
    category: Optional[str] = None,
    city: Optional[str] = None,
    scheme: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = 100,
) -> str:
    """List points of interest, filtered by category / city / scheme / free text."""
    city_obj = resolve_city(city) if city else None
    scheme_obj = resolve_scheme(scheme) if scheme else None
    rows = _poi_filter(category=category, city_id=city_obj.id if city_obj else None,
                       scheme_id=scheme_obj.id if scheme_obj else None, query=query)
    rows = rows[:limit]
    return dump({"count": len(rows), "pois": [_poi_view(p) for p in rows]})


@mcp.tool()
def poi_get(poi_id: str) -> str:
    """Fetch one point of interest by id."""
    poi = next((p for p in pois_db if p.id == poi_id), None)
    if not poi:
        return dump({"error": f"POI not found: {poi_id}"})
    return dump(_poi_view(poi))


@mcp.tool()
def poi_update(
    poi_id: str,
    name: Optional[str] = None,
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    address: Optional[str] = None,
    rating: Optional[float] = None,
    importance: Optional[float] = None,
    tags: Optional[List[str]] = None,
) -> str:
    """Update a point of interest."""
    poi = next((p for p in pois_db if p.id == poi_id), None)
    if not poi:
        return dump({"error": f"POI not found: {poi_id}"})
    if category is not None:
        if category not in POI_CATEGORIES:
            return dump({"error": f"category must be one of {POI_CATEGORIES}"})
        poi.category = category
    for field, value in (("name", name), ("subcategory", subcategory), ("latitude", latitude),
                         ("longitude", longitude), ("address", address), ("rating", rating),
                         ("importance", importance)):
        if value is not None:
            setattr(poi, field, value)
    if tags is not None:
        poi.tags = tags
    poi.updated_at = datetime.now()
    return dump(_poi_view(poi))


@mcp.tool()
def poi_delete(poi_id: str) -> str:
    """Delete a point of interest."""
    before = len(pois_db)
    pois_db[:] = [p for p in pois_db if p.id != poi_id]
    if len(pois_db) == before:
        return dump({"error": f"POI not found: {poi_id}"})
    return dump({"deleted": True, "poi_id": poi_id, "remaining": len(pois_db)})


@mcp.tool()
def poi_categories() -> str:
    """Every POI category with its count, liveability weight and average rating."""
    out = []
    for cat in POI_CATEGORIES:
        rows = [p for p in pois_db if p.category == cat]
        ratings = [p.rating for p in rows if p.rating is not None]
        out.append(
            {
                "category": cat,
                "count": len(rows),
                "weight": POI_CATEGORY_WEIGHTS.get(cat, 0.3),
                "avg_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
            }
        )
    out.sort(key=lambda r: -r["count"])
    return dump({"count": len(pois_db), "categories": out})


@mcp.tool()
def poi_nearby(
    latitude: float,
    longitude: float,
    radius_km: float = 2.0,
    category: Optional[str] = None,
    limit: int = 50,
) -> str:
    """Points of interest within ``radius_km`` of a point, nearest first."""
    rows = _poi_near(latitude, longitude, radius_km * 1000.0, category=category)[:limit]
    return dump(
        {
            "center": {"latitude": latitude, "longitude": longitude},
            "radius_km": radius_km,
            "count": len(rows),
            "pois": rows,
        }
    )


@mcp.tool()
def poi_nearest(latitude: float, longitude: float, radius_km: float = 25.0) -> str:
    """The single nearest POI in every category (handy for a liveability panel)."""
    rows = _poi_nearest_by_category(latitude, longitude, radius_km * 1000.0)
    return dump({"center": {"latitude": latitude, "longitude": longitude}, "count": len(rows), "nearest": rows})


@mcp.tool()
def poi_within_polygon(coordinates: List[List[float]], category: Optional[str] = None) -> str:
    """Points of interest inside a polygon (``[[lat, lon], ...]``)."""
    if len(coordinates) < 3:
        return dump({"error": "Provide at least 3 [lat, lon] pairs"})
    ring = gis.coords_from_latlon_list(coordinates)
    rows = [
        _poi_view(poi) for poi in _poi_filter(category=category)
        if gis.point_in_polygon(poi.latitude, poi.longitude, ring)
    ]
    area_sqm = gis.polygon_area_sqm(ring)
    return dump(
        {
            "count": len(rows),
            "area_sqm": round(area_sqm, 2),
            "pois": rows,
        }
    )


@mcp.tool()
def poi_density(entity_type: str, entity_id: str) -> str:
    """POI mix and density (per km²) inside an entity's footprint."""
    props = _entity_properties(entity_type, entity_id)
    geom = _entity_geometry(entity_type, entity_id, props)
    ring = _geom_ring(geom)
    inside = [p for p in pois_db if ring and gis.point_in_polygon(p.latitude, p.longitude, ring)]
    area_sqm = _geometry_area_sqm(geom) or 0.0
    area_km2 = area_sqm / 1_000_000 if area_sqm else 0.0
    counts: Dict[str, int] = {}
    for p in inside:
        counts[p.category] = counts.get(p.category, 0) + 1
    _, _, name = _entity_center(entity_type, entity_id)
    return dump(
        {
            "entity": {"type": entity_type, "id": entity_id, "name": name},
            "area_km2": round(area_km2, 4),
            "total_pois": len(inside),
            "density_per_sqkm": round(len(inside) / area_km2, 1) if area_km2 else None,
            "by_category": {k: {"count": v, "per_sqkm": round(v / area_km2, 1) if area_km2 else None}
                            for k, v in sorted(counts.items(), key=lambda kv: -kv[1])},
        }
    )


@mcp.tool()
def poi_accessibility_score(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    radius_km: float = 3.0,
) -> str:
    """Distance-decayed liveability / accessibility score (0-100) for an entity or a point."""
    if entity_type and entity_id:
        lat, lon, name = _entity_center(entity_type, entity_id)
    else:
        lat, lon, name = latitude, longitude, "point"
    if lat is None or lon is None:
        return dump({"error": "Provide entity_type+entity_id or latitude+longitude"})
    score = _poi_accessibility(lat, lon, radius_km * 1000.0)
    score["name"] = name
    score["entity"] = {"type": entity_type, "id": entity_id} if entity_type else None
    return dump(score)


@mcp.tool()
def poi_map(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    radius_km: float = 2.0,
    categories: Optional[List[str]] = None,
    limit: int = 60,
    base_map: Optional[str] = None,
    lang: str = gis.DEFAULT_LANGUAGE,
    theme: str = gis.DEFAULT_THEME,
) -> str:
    """Self-contained HTML map of points of interest around an entity or a point."""
    city_id = None
    if entity_type and entity_id:
        lat, lon, name = _entity_center(entity_type, entity_id)
        if entity_type == "city":
            city_id = entity_id
        elif entity_type == "scheme":
            s = find_scheme(entity_id)
            city_id = s.city_id if s else None
    else:
        lat, lon, name = latitude, longitude, "Points of interest"
    if lat is None or lon is None:
        return dump({"error": "Provide entity_type+entity_id or latitude+longitude"})

    if entity_type and entity_id:
        rows = [
            {"name": p.name, "lat": p.latitude, "lon": p.longitude, "description": p.category,
             "distance_m": round(gis.haversine_m(lat, lon, p.latitude, p.longitude), 1)}
            for p in _poi_filter(categories=categories, city_id=city_id)
        ]
        rows.sort(key=lambda r: r["distance_m"])
    else:
        rows = [
            {"name": p["name"], "lat": p["latitude"], "lon": p["longitude"],
             "description": p["category"], "distance_m": p["distance_m"]}
            for p in _poi_near(lat, lon, radius_km * 1000.0, categories=categories)
        ]
    rows = rows[:limit]

    overlays = []
    if entity_type and entity_id:
        layers = [l for l in gis.list_layers(entity_type=entity_type, entity_id=entity_id) if l.visible]
        overlays = [{"name": l.name, "geojson": l.geojson, "style": l.style} for l in layers]

    return gis.build_map_html(
        title=f"{name} — POI",
        center_lat=lat,
        center_lon=lon,
        zoom=14,
        base_map_id=base_map or gis.DEFAULT_BASE_MAP,
        overlays=overlays,
        markers=rows,
        lang=lang,
        theme=theme,
    )


@mcp.resource("poi://all", name="All POIs", description="Every point of interest.")
def res_poi_all() -> str:
    return poi_list(limit=500)


@mcp.resource("poi://categories", name="POI categories", description="POI categories with counts and weights.")
def res_poi_categories() -> str:
    return poi_categories()


@mcp.tool()
def aoi_create(
    name: str,
    kind: str = "circle",
    description: Optional[str] = None,
    center_latitude: Optional[float] = None,
    center_longitude: Optional[float] = None,
    radius_m: Optional[float] = None,
    coordinates: Optional[List[List[float]]] = None,
    bounds: Optional[Dict[str, float]] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    city: Optional[str] = None,
    scheme: Optional[str] = None,
    tags: Optional[List[str]] = None,
    watch_categories: Optional[List[str]] = None,
    watch_alert_threshold: float = 0.0,
    created_by: Optional[str] = None,
    notes: Optional[str] = None,
) -> str:
    """Save an area of interest: ``circle`` (centre + radius), ``polygon`` ([[lat, lon], ...]),
    ``bbox`` ({south, west, north, east}) or ``entity`` (city/scheme/block/bigproject)."""
    if kind not in AOI_KINDS:
        return dump({"error": f"kind must be one of {AOI_KINDS}"})
    city_obj = resolve_city(city) if city else None
    scheme_obj = resolve_scheme(scheme) if scheme else None
    aoi = AreaOfInterest(
        name=name, description=description, kind=kind,
        center_latitude=center_latitude, center_longitude=center_longitude, radius_m=radius_m,
        coordinates=coordinates or [], bounds=bounds,
        entity_type=entity_type, entity_id=entity_id,
        city_id=city_obj.id if city_obj else None,
        scheme_id=scheme_obj.id if scheme_obj else None,
        tags=tags or [], watch_categories=watch_categories or [],
        watch_alert_threshold=watch_alert_threshold, created_by=created_by, notes=notes,
    )
    if _aoi_geometry(aoi) is None:
        return dump({"error": "Could not resolve a geometry — check kind and its parameters"})
    aois_db.append(aoi)
    return dump(_aoi_view(aoi))


@mcp.tool()
def aoi_list(kind: Optional[str] = None, city: Optional[str] = None, scheme: Optional[str] = None) -> str:
    """List saved areas of interest."""
    city_obj = resolve_city(city) if city else None
    scheme_obj = resolve_scheme(scheme) if scheme else None
    rows = list(aois_db)
    if kind:
        rows = [a for a in rows if a.kind == kind]
    if city_obj:
        rows = [a for a in rows if a.city_id == city_obj.id]
    if scheme_obj:
        rows = [a for a in rows if a.scheme_id == scheme_obj.id]
    return dump({"count": len(rows), "areas": [_aoi_view(a) for a in rows]})


@mcp.tool()
def aoi_get(aoi_id: str) -> str:
    """Fetch one area of interest (by id or name) with its resolved geometry."""
    aoi = _find_aoi(aoi_id)
    if not aoi:
        return dump({"error": f"Area of interest not found: {aoi_id}"})
    return dump(_aoi_view(aoi))


@mcp.tool()
def aoi_update(
    aoi_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    tags: Optional[List[str]] = None,
    watch_categories: Optional[List[str]] = None,
    watch_alert_threshold: Optional[float] = None,
    notes: Optional[str] = None,
) -> str:
    """Rename, re-tag or re-configure the news watch of an area of interest."""
    aoi = _find_aoi(aoi_id)
    if not aoi:
        return dump({"error": f"Area of interest not found: {aoi_id}"})
    for field, value in (("name", name), ("description", description), ("notes", notes)):
        if value is not None:
            setattr(aoi, field, value)
    if tags is not None:
        aoi.tags = tags
    if watch_categories is not None:
        aoi.watch_categories = watch_categories
    if watch_alert_threshold is not None:
        aoi.watch_alert_threshold = watch_alert_threshold
    aoi.updated_at = datetime.now()
    return dump(_aoi_view(aoi))


@mcp.tool()
def aoi_delete(aoi_id: str) -> str:
    """Delete an area of interest."""
    before = len(aois_db)
    aois_db[:] = [a for a in aois_db if a.id != aoi_id and a.name.lower() != str(aoi_id).lower()]
    if len(aois_db) == before:
        return dump({"error": f"Area of interest not found: {aoi_id}"})
    return dump({"deleted": True, "aoi_id": aoi_id, "remaining": len(aois_db)})


@mcp.tool()
def aoi_stats(aoi_id: str) -> str:
    """Quick statistics for an area of interest: area, properties, value, population, POIs."""
    aoi = _find_aoi(aoi_id)
    if not aoi:
        return dump({"error": f"Area of interest not found: {aoi_id}"})
    props = _aoi_properties(aoi)
    geom = _aoi_geometry(aoi)
    analysis = _area_analysis(aoi.name, props, geometry=geom)
    pois = _aoi_pois(aoi)
    counts: Dict[str, int] = {}
    for poi in pois:
        counts[poi.category] = counts.get(poi.category, 0) + 1
    lat, lon, _ = _aoi_center(aoi)
    return dump(
        {
            "id": aoi.id,
            "name": aoi.name,
            "kind": aoi.kind,
            "area": analysis["area"],
            "properties": analysis["properties"]["count"],
            "market_value": analysis["properties"]["total_market_value"],
            "population": analysis["population"]["population_from_listings"],
            "density_per_sqkm": analysis["population"]["density_per_sqkm"],
            "development_cost": analysis["development_cost"]["total"],
            "pois": len(pois),
            "poi_by_category": counts,
            "accessibility": _poi_accessibility(lat, lon)["score"] if lat is not None else None,
            "center": {"latitude": lat, "longitude": lon},
        }
    )


@mcp.tool()
def aoi_analyze(aoi_id: str, years: int = 5) -> str:
    """Full analytics for an area of interest: area & valuation, population, cost & economic
    impact, POI mix, accessibility, factor scores, future predictions and related news."""
    aoi = _find_aoi(aoi_id)
    if not aoi:
        return dump({"error": f"Area of interest not found: {aoi_id}"})
    props = _aoi_properties(aoi)
    geom = _aoi_geometry(aoi)
    analysis = _area_analysis(aoi.name, props, geometry=geom)
    cost_dev = _cost_development_analysis(analysis, 0.0, None)
    lat, lon, _ = _aoi_center(aoi)
    scope_type, scope_id = _aoi_scope(aoi)
    scores = _factor_dict(_find_factor(scope_type, scope_id))
    news_summary = _news_sentiment(city_id=aoi.city_id, scheme_id=aoi.scheme_id)
    forecast = _forecast(analysis, scores, news_summary, years=years)
    pois = _aoi_pois(aoi)
    counts: Dict[str, int] = {}
    for poi in pois:
        counts[poi.category] = counts.get(poi.category, 0) + 1
    return dump(
        {
            "area_of_interest": _aoi_view(aoi),
            "analysis": analysis,
            "cost_development": cost_dev,
            "poi_summary": {
                "total": len(pois),
                "by_category": counts,
                "accessibility": _poi_accessibility(lat, lon) if lat is not None else None,
            },
            "factors": {"scope": {"scope_type": scope_type, "scope_id": scope_id},
                        "index": _composite_index(scores), "scores": scores},
            "forecast": forecast,
            "news": [_news_item_view(n) for n in _news_filter(city_id=aoi.city_id, scheme_id=aoi.scheme_id)[:10]],
        }
    )


def _news_item_view(n: NewsItem) -> Dict[str, Any]:
    return {
        "title": n.title, "source": n.source, "category": n.category, "sentiment": n.sentiment,
        "impact_score": n.impact_score, "published_at": n.published_at.isoformat(), "url": n.url,
    }


@mcp.tool()
def aoi_compare(aoi_ids: List[str]) -> str:
    """Compare two or more areas of interest side by side."""
    rows = []
    for aid in aoi_ids:
        aoi = _find_aoi(aid)
        if not aoi:
            rows.append({"aoi_id": aid, "error": "not found"})
            continue
        stats = json.loads(aoi_stats(aoi.id))
        rows.append(
            {
                "aoi_id": aoi.id,
                "name": aoi.name,
                "kind": aoi.kind,
                "area_marla": stats["area"]["area_marla"],
                "properties": stats["properties"],
                "market_value": stats["market_value"],
                "population": stats["population"],
                "density_per_sqkm": stats["density_per_sqkm"],
                "development_cost": stats["development_cost"],
                "pois": stats["pois"],
                "accessibility": stats["accessibility"],
            }
        )
    return dump({"count": len(rows), "comparison": rows})


@mcp.tool()
def aoi_watch(aoi_id: str, days: int = 120) -> str:
    """News watch: relevant headlines for an area plus alerts when the impact of a
    watched category exceeds the configured threshold."""
    aoi = _find_aoi(aoi_id)
    if not aoi:
        return dump({"error": f"Area of interest not found: {aoi_id}"})
    items = _news_filter(city_id=aoi.city_id, scheme_id=aoi.scheme_id, days=days)
    if aoi.watch_categories:
        items = [n for n in items if n.category in aoi.watch_categories]
    summary = _news_sentiment(city_id=aoi.city_id, scheme_id=aoi.scheme_id, days=days)
    alerts = [
        _news_item_view(n) for n in items
        if abs(n.impact_score) >= (aoi.watch_alert_threshold or 0.0)
    ]
    return dump(
        {
            "area_of_interest": {"id": aoi.id, "name": aoi.name, "watch_categories": aoi.watch_categories,
                                 "watch_alert_threshold": aoi.watch_alert_threshold},
            "summary": summary,
            "count": len(items),
            "alerts": alerts,
            "news": [_news_item_view(n) for n in items[:20]],
        }
    )


@mcp.tool()
def aoi_report(
    aoi_id: str,
    years: int = 5,
    include_map: bool = True,
    include_news: bool = True,
    lang: str = gis.DEFAULT_LANGUAGE,
    theme: str = gis.DEFAULT_THEME,
) -> str:
    """Printable HTML report for an area of interest (analysis + POI + outlook + ticker)."""
    aoi = _find_aoi(aoi_id)
    if not aoi:
        return dump({"error": f"Area of interest not found: {aoi_id}"})
    props = _aoi_properties(aoi)
    geom = _aoi_geometry(aoi)
    analysis = _area_analysis(aoi.name, props, geometry=geom)
    cost_dev = _cost_development_analysis(analysis, 0.0, None)
    scope_type, scope_id = _aoi_scope(aoi)
    scores = _factor_dict(_find_factor(scope_type, scope_id))
    news_summary = _news_sentiment(city_id=aoi.city_id, scheme_id=aoi.scheme_id)
    forecast = _forecast(analysis, scores, news_summary, years=years)
    news_items = _news_filter(city_id=aoi.city_id, scheme_id=aoi.scheme_id)[:12]
    pois = _aoi_pois(aoi)
    counts: Dict[str, int] = {}
    for poi in pois:
        counts[poi.category] = counts.get(poi.category, 0) + 1
    lat, lon, _ = _aoi_center(aoi)
    accessibility = _poi_accessibility(lat, lon) if lat is not None else None

    poi_section = {
        "heading": "Points of interest",
        "kind": "pills",
        "items": [[k, str(v)] for k, v in sorted(counts.items(), key=lambda kv: -kv[1])]
        or [["No POIs registered", "0"]],
        "note": f"Accessibility score {accessibility['score']} ({accessibility['band']})"
        if accessibility else None,
    }
    access_section = {
        "heading": "Accessibility by category",
        "kind": "table",
        "columns": ["Category", "Count", "Nearest (m)", "Score"],
        "rows": [
            [k, str(v["count"]), f"{v['nearest_m']:,.0f}", f"{v['score']:.1f}"]
            for k, v in (accessibility or {}).get("by_category", {}).items()
        ] or [["–", "0", "–", "0"]],
    }

    sections = (
        _report_sections(analysis)
        + [poi_section, access_section]
        + _outlook_sections(analysis, cost_dev, forecast, news_summary, news_items)
    )
    ticker = gis.build_ticker_html([model_dict(n) for n in news_items], label="Real Estate News", lang=lang) if include_news else ""
    map_html = None
    if include_map:
        map_html = aoi_map(aoi_id, lang=lang, theme=theme)
    return gis.build_report_html(
        title=f"{aoi.name} — {gis.translate('Area of Interest', lang)}",
        subtitle=f"{aoi.kind} · index {forecast['composite_index']} ({forecast['index_band']}) · "
        f"base CAGR {forecast['base_cagr']:.1%} · {len(props)} properties · {len(pois)} POIs",
        sections=sections,
        map_html=map_html,
        ticker_html=ticker,
        lang=lang,
        theme=theme,
    )


@mcp.tool()
def aoi_map(
    aoi_id: str,
    base_map: Optional[str] = None,
    include_properties: bool = True,
    include_pois: bool = True,
    lang: str = gis.DEFAULT_LANGUAGE,
    theme: str = gis.DEFAULT_THEME,
) -> str:
    """Self-contained HTML map of an area of interest with its boundary, properties and POIs."""
    aoi = _find_aoi(aoi_id)
    if not aoi:
        return dump({"error": f"Area of interest not found: {aoi_id}"})
    lat, lon, _ = _aoi_center(aoi)
    if lat is None or lon is None:
        return dump({"error": "Area of interest has no resolvable centre"})
    geom = _aoi_geometry(aoi)

    overlays = []
    if geom:
        overlays.append(
            {
                "name": aoi.name,
                "geojson": gis.feature_collection(
                    [{"type": "Feature", "geometry": geom,
                      "properties": {"name": aoi.name, "kind": aoi.kind}}]
                ),
                "style": {"color": "#e6194b", "fillColor": "#e6194b", "fillOpacity": 0.12,
                          "weight": 3, "opacity": 0.95},
            }
        )
    markers = []
    if include_properties:
        for p in _aoi_properties(aoi):
            if p.latitude is not None and p.longitude is not None:
                markers.append({"lat": p.latitude, "lon": p.longitude, "title": p.title,
                                "description": f"{p.price:,.0f} {p.currency}"})
    if include_pois:
        for poi in _aoi_pois(aoi):
            markers.append({"lat": poi.latitude, "lon": poi.longitude,
                            "title": f"POI: {poi.name}", "description": poi.category})

    zoom = 15 if aoi.kind == "circle" else 13
    return gis.build_map_html(
        title=aoi.name,
        center_lat=lat,
        center_lon=lon,
        zoom=zoom,
        base_map_id=base_map or gis.DEFAULT_BASE_MAP,
        overlays=overlays,
        markers=markers,
        lang=lang,
        theme=theme,
    )


@mcp.resource("aoi://all", name="All AOIs", description="Every saved area of interest.")
def res_aoi_all() -> str:
    return aoi_list()


@mcp.resource("aoi://categories", name="AOI kinds", description="Supported area-of-interest kinds.")
def res_aoi_kinds() -> str:
    return dump({"kinds": AOI_KINDS, "count": len(aois_db)})


@mcp.prompt(name="aoi_due_diligence_prompt", description="Run due diligence on an area of interest.")
def prompt_aoi_due_diligence(aoi_id: str) -> str:
    return (
        "Act as a property due-diligence analyst.\n"
        f"Run aoi_analyze, aoi_watch, poi_density and gis_forecast for area {aoi_id}.\n"
        "Assess demand, infrastructure, liveability (POI mix), development pipeline, regulatory and "
        "political risk, then produce a go / no-go recommendation with the key risks and mitigations."
    )


@mcp.prompt(name="site_selection_prompt", description="Shortlist the best site for a given use.")
def prompt_site_selection(city: str = "Lahore", use_type: str = "residential", budget: str = "any") -> str:
    return (
        "You are a real-estate site-selection consultant.\n"
        f"City: {city}. Intended use: {use_type}. Budget: {budget}.\n"
        "1. Use search_properties and global_search to map the options.\n"
        "2. Use gis_forecast, gis_market_factors, poi_accessibility_score and gis_cost_development_analysis "
        "to score each candidate site.\n"
        "3. Rank the sites and justify the top three with numbers (index, CAGR, yield, cost)."
    )


# ============================================================
# ============ ROUTING (on foot / car: best + alternatives) ===
# ============================================================


road_networks_db: Dict[str, gis.RoadNetwork] = {}


def _scope_points(city_obj: Optional[City] = None, scheme_obj: Optional[HousingScheme] = None) -> List[Tuple[float, float]]:
    pts: List[Tuple[float, float]] = []
    for p in properties_db:
        if p.latitude is None or p.longitude is None:
            continue
        if city_obj and p.city_id != city_obj.id:
            continue
        if scheme_obj and p.scheme_id != scheme_obj.id:
            continue
        pts.append((p.latitude, p.longitude))
    for poi in pois_db:
        if city_obj and poi.city_id != city_obj.id:
            continue
        if scheme_obj and poi.scheme_id != scheme_obj.id:
            continue
        pts.append((poi.latitude, poi.longitude))
    if not pts:
        if scheme_obj and scheme_obj.latitude is not None:
            pts.append((scheme_obj.latitude, scheme_obj.longitude))
        elif city_obj:
            pts.append((city_obj.latitude, city_obj.longitude))
    if not pts:
        pts = [(31.5204, 74.3587)]
    return pts


def get_road_network(city_obj: Optional[City] = None, scheme_obj: Optional[HousingScheme] = None,
                     name: Optional[str] = None,
                     points: Optional[List[Tuple[float, float]]] = None) -> gis.RoadNetwork:
    """Return a cached synthetic street grid covering a scope or a set of points.

    A caller-supplied network registered with ``gis_add_road_network`` is used when
    ``name`` matches; otherwise a grid is generated over the bounding box of
    ``points`` (or of the city / scheme scope). The grid is capped in size so a
    nationwide bounding box never explodes into hundreds of thousands of nodes.
    """
    if name and name in road_networks_db:
        return road_networks_db[name]
    if not points and not name:
        if scheme_obj:
            key_check = f"scheme:{scheme_obj.id}"
            if key_check in road_networks_db:
                return road_networks_db[key_check]
        elif city_obj:
            key_check = f"city:{city_obj.id}"
            if key_check in road_networks_db:
                return road_networks_db[key_check]
    pts = list(points) if points else _scope_points(city_obj, scheme_obj)
    lats = [p[0] for p in pts]
    lons = [p[1] for p in pts]
    pad = 0.018
    south, north = min(lats) - pad, max(lats) + pad
    west, east = min(lons) - pad, max(lons) + pad
    # keep the grid meaningful for a single point / short hop
    if north - south < 0.05:
        mid = (south + north) / 2
        south, north = mid - 0.025, mid + 0.025
    if east - west < 0.05:
        mid = (west + east) / 2
        west, east = mid - 0.025, mid + 0.025

    # choose a spacing that keeps the node count sane for large spans
    spacing = float(gis.ROUTE_CONFIG["grid_spacing_m"])
    mid_lat = (south + north) / 2.0
    max_nodes = 20000
    for _ in range(24):
        rows = (north - south) / (spacing / 111320.0) + 1
        cols = (east - west) / (spacing / (111320.0 * max(0.15, math.cos(math.radians(mid_lat))))) + 1
        if rows * cols <= max_nodes:
            break
        spacing *= 1.5

    key = name or (f"scheme:{scheme_obj.id}" if scheme_obj
                   else f"city:{city_obj.id}" if city_obj
                   else f"pts:{south:.3f},{west:.3f},{north:.3f},{east:.3f}")
    if key in road_networks_db and not name:
        return road_networks_db[key]
    net = gis.build_grid_network(south, west, north, east, spacing_m=spacing, name=key)
    road_networks_db[key] = net
    return net


def _route_network(city_obj: Optional[City], scheme_obj: Optional[HousingScheme],
                   network: Optional[str], *coords: Tuple[float, float]) -> gis.RoadNetwork:
    """Resolve a routing network: a registered/scope network, else a local grid."""
    if network or city_obj or scheme_obj:
        return get_road_network(city_obj, scheme_obj, name=network)
    return get_road_network(points=[(float(c[0]), float(c[1])) for c in coords if c])


def _find_poi(ref: str) -> Optional[PointOfInterest]:
    if not ref:
        return None
    r = str(ref).strip().lower()
    return next((p for p in pois_db if p.id == ref or p.name.lower() == r), None) \
        or next((p for p in pois_db if r in p.name.lower()), None)


@mcp.tool()
def gis_travel_modes() -> str:
    """The available travel modes (on foot, bicycle, motor car) and their road speeds."""
    return dump({"default": gis.ROUTE_CONFIG["default_mode"], "modes": gis.travel_modes(),
                 "config": gis.ROUTE_CONFIG})


@mcp.tool()
def gis_road_classes() -> str:
    """Road classes with their per-mode speeds (0 = the mode may not use that class)."""
    return dump({"count": len(gis.ROAD_CLASSES), "road_classes": gis.road_classes(),
                 "config": gis.ROUTE_CONFIG})


@mcp.tool()
def gis_add_road_network(
    name: str,
    ways: Optional[List[Dict[str, Any]]] = None,
    description: Optional[str] = None,
) -> str:
    """Register a custom routable road network from ``ways`` (polylines).

    Each way: ``{coordinates: [[lat, lon], ...], road_class: arterial|local|footpath|…,
    name?: str, one_way?: bool}``. Once registered, pass its ``name`` to the routing
    tools to use it instead of the synthetic grid.
    """
    net = gis.network_from_ways(ways or [], name=name)
    if not net.nodes:
        return dump({"error": "No ways supplied — a network needs at least one polyline"})
    road_networks_db[name] = net
    info = net.info()
    info["description"] = description
    return dump(info)


@mcp.tool()
def gis_list_road_networks() -> str:
    """List the road networks currently available for routing."""
    return dump({"count": len(road_networks_db),
                 "networks": [n.info() for n in road_networks_db.values()]})


@mcp.tool()
def gis_route(
    origin_latitude: float,
    origin_longitude: float,
    destination_latitude: float,
    destination_longitude: float,
    mode: str = "drive",
    alternatives: int = 2,
    traffic_factor: Optional[float] = None,
    city: Optional[str] = None,
    scheme: Optional[str] = None,
    network: Optional[str] = None,
    origin_label: Optional[str] = None,
    destination_label: Optional[str] = None,
) -> str:
    """Best route (plus alternatives) between two points by ``walk`` / ``bike`` / ``drive``.

    Returns distance, duration, turn-by-turn steps, the route geometry and the
    per-road-class breakdown. ``traffic_factor`` scales driving times only.
    """
    city_obj = resolve_city(city) if city else None
    scheme_obj = resolve_scheme(scheme) if scheme else None
    net = _route_network(city_obj, scheme_obj, network,
                         (origin_latitude, origin_longitude),
                         (destination_latitude, destination_longitude))
    return dump(gis.route(
        net, (origin_latitude, origin_longitude), (destination_latitude, destination_longitude),
        mode=mode, alternatives=alternatives, traffic_factor=traffic_factor,
        origin_label=origin_label or "Origin", destination_label=destination_label or "Destination",
    ))


@mcp.tool()
def poi_route(
    origin_poi: str,
    destination_poi: str,
    mode: str = "drive",
    alternatives: int = 2,
    traffic_factor: Optional[float] = None,
    network: Optional[str] = None,
) -> str:
    """Route between two points of interest (by id or name), on foot or by car."""
    a = _find_poi(origin_poi)
    b = _find_poi(destination_poi)
    if not a or not b:
        return dump({"error": f"POI not found: {origin_poi if not a else destination_poi}"})
    net = _route_network(None, None, network, (a.latitude, a.longitude), (b.latitude, b.longitude))
    result = gis.route(
        net, (a.latitude, a.longitude), (b.latitude, b.longitude), mode=mode,
        alternatives=alternatives, traffic_factor=traffic_factor,
        origin_label=a.name, destination_label=b.name,
    )
    result["origin_poi"] = {"id": a.id, "name": a.name, "category": a.category}
    result["destination_poi"] = {"id": b.id, "name": b.name, "category": b.category}
    return dump(result)


@mcp.tool()
def gis_route_compare(
    origin_latitude: float,
    origin_longitude: float,
    destination_latitude: float,
    destination_longitude: float,
    modes: Optional[List[str]] = None,
    city: Optional[str] = None,
    scheme: Optional[str] = None,
    network: Optional[str] = None,
) -> str:
    """Compare every travel mode (on foot / bicycle / motor car) between two points."""
    city_obj = resolve_city(city) if city else None
    scheme_obj = resolve_scheme(scheme) if scheme else None
    net = _route_network(city_obj, scheme_obj, network,
                         (origin_latitude, origin_longitude),
                         (destination_latitude, destination_longitude))
    return dump(gis.compare_modes(
        net, (origin_latitude, origin_longitude), (destination_latitude, destination_longitude),
        modes=modes, alternatives=1,
    ))


@mcp.tool()
def gis_route_matrix(
    poi_ids: Optional[List[str]] = None,
    coordinates: Optional[List[List[float]]] = None,
    mode: str = "drive",
    city: Optional[str] = None,
    scheme: Optional[str] = None,
    network: Optional[str] = None,
) -> str:
    """Distance/time matrix between a set of POIs (by id/name) or raw ``[lat, lon]`` points."""
    labels: List[str] = []
    points: List[Tuple[float, float]] = []
    for ref in poi_ids or []:
        poi = _find_poi(ref)
        if poi:
            points.append((poi.latitude, poi.longitude))
            labels.append(poi.name)
    for pair in coordinates or []:
        if len(pair) >= 2:
            points.append((float(pair[0]), float(pair[1])))
            labels.append(f"{pair[0]:.4f},{pair[1]:.4f}")
    if len(points) < 2:
        return dump({"error": "Provide at least two POI ids or coordinates"})
    city_obj = resolve_city(city) if city else None
    scheme_obj = resolve_scheme(scheme) if scheme else None
    net = _route_network(city_obj, scheme_obj, network, *points)
    matrix = []
    for i, row in enumerate(points):
        cells = []
        for j, col in enumerate(points):
            if i == j:
                cells.append({"distance_km": 0.0, "duration_min": 0.0})
                continue
            r = gis.route(net, row, col, mode=mode, alternatives=0)
            b = r.get("best", {})
            cells.append({"distance_km": b.get("distance_km"), "duration_min": b.get("duration_min"),
                          "duration_text": b.get("duration_text")})
        matrix.append({"from": labels[i], "to": cells})
    return dump({"mode": mode, "mode_label": gis.TRAVEL_MODES.get(mode, {}).get("label", mode),
                 "points": labels, "matrix": matrix})


@mcp.tool()
def gis_route_map(
    origin_latitude: float,
    origin_longitude: float,
    destination_latitude: float,
    destination_longitude: float,
    mode: str = "drive",
    alternatives: int = 2,
    include_compare: bool = True,
    ticker: bool = False,
    base_map: Optional[str] = None,
    city: Optional[str] = None,
    scheme: Optional[str] = None,
    network: Optional[str] = None,
    lang: str = "en",
    theme: str = "auto",
) -> str:
    """Interactive map (HTML) of the best route and its alternatives, by foot or car."""
    city_obj = resolve_city(city) if city else None
    scheme_obj = resolve_scheme(scheme) if scheme else None
    origin = (origin_latitude, origin_longitude)
    dest = (destination_latitude, destination_longitude)
    net = _route_network(city_obj, scheme_obj, network, origin, dest)
    result = gis.route(net, origin, dest, mode=mode, alternatives=alternatives,
                       origin_label="Origin", destination_label="Destination")
    if "error" in result:
        return dump(result)
    routes = [result["best"], *result["alternatives"]]
    overlays = gis.route_overlays(routes)
    markers = [
        {"lat": origin[0], "lon": origin[1], "title": "Origin",
         "description": f"{result['best']['distance_km']} km · {result['best']['duration_text']}"},
        {"lat": dest[0], "lon": dest[1], "title": "Destination", "description": result["mode_label"]},
    ]
    if include_compare:
        cmp_rows = gis.compare_modes(net, origin, dest)["modes"]
        for m, row in cmp_rows.items():
            if "duration_text" in row:
                markers.append({
                    "lat": origin[0], "lon": origin[1],
                    "title": f"{row['mode_label']}: {row['distance_km']} km",
                    "description": f"{row['duration_text']} ({m})",
                })
    center = ((origin[0] + dest[0]) / 2, (origin[1] + dest[1]) / 2)
    return gis.build_map_html(
        title=f"{result['mode_label']} route",
        center_lat=center[0], center_lon=center[1], zoom=13,
        base_map_id=base_map or gis.DEFAULT_BASE_MAP,
        overlays=overlays, markers=markers,
        ticker_html=_portal_ticker(lang) if ticker else "",
        lang=lang, theme=theme,
    )


# ============================================================
# ============ PORTAL USERS & ROLES (RBAC) ===================
# ============================================================


@mcp.tool()
def auth_role_summary() -> str:
    """Roles by portal area, the permission catalogue size and per-role member counts."""
    return dump(auth.role_summary())


@mcp.tool()
def auth_list_roles(portal_area: Optional[str] = None) -> str:
    """List portal roles (public / client / staff / admin) with their permissions."""
    return dump({"count": len(auth.list_roles(portal_area)),
                 "portal_areas": auth.PORTAL_AREAS,
                 "roles": auth.list_roles(portal_area)})


@mcp.tool()
def auth_get_role(name: str) -> str:
    """Fetch one role with its full permission list and member count."""
    role = auth.get_role(name)
    if not role:
        return dump({"error": f"Role not found: {name}",
                     "known": [r["name"] for r in auth.list_roles()]})
    return dump(auth.role_view(role))


@mcp.tool()
def auth_permissions() -> str:
    """The full permission catalogue (resource.action) with descriptions."""
    return dump({"count": len(auth.PERMISSIONS), "permissions": auth.list_permissions()})


@mcp.tool()
def auth_create_role(
    name: str,
    label: str,
    description: Optional[str] = None,
    portal_area: str = "staff",
    level: int = 20,
    permissions: Optional[List[str]] = None,
) -> str:
    """Create a custom portal role from a set of permissions."""
    return dump(auth.create_role(name=name, label=label, description=description,
                                 portal_area=portal_area, level=level, permissions=permissions))


@mcp.tool()
def auth_update_role(
    name: str,
    label: Optional[str] = None,
    description: Optional[str] = None,
    portal_area: Optional[str] = None,
    level: Optional[int] = None,
    permissions: Optional[List[str]] = None,
) -> str:
    """Update a role (system roles keep their permissions but may be re-labelled)."""
    return dump(auth.update_role(name=name, label=label, description=description,
                                 portal_area=portal_area, level=level, permissions=permissions))


@mcp.tool()
def auth_delete_role(name: str) -> str:
    """Delete a custom role (system or in-use roles are protected)."""
    return dump(auth.delete_role(name))


@mcp.tool()
def auth_set_user_roles(user_id: str, roles: List[str]) -> str:
    """Replace a user's full role set (the highest-level role becomes primary)."""
    return dump(auth.set_roles(user_id, roles))


@mcp.tool()
def auth_assign_role(user_id: str, role: str) -> str:
    """Grant one role to a portal user."""
    return dump(auth.assign_role(user_id, role))


@mcp.tool()
def auth_revoke_role(user_id: str, role: str) -> str:
    """Remove one role from a portal user (a user always keeps at least one)."""
    return dump(auth.revoke_role(user_id, role))


@mcp.tool()
def auth_grant_permission(user_id: str, permission: str) -> str:
    """Grant one extra permission directly to a user, on top of their roles."""
    return dump(auth.grant_permission(user_id, permission))


@mcp.tool()
def auth_revoke_permission(user_id: str, permission: str) -> str:
    """Withdraw a directly-granted permission from a user."""
    return dump(auth.revoke_permission(user_id, permission))


@mcp.tool()
def auth_check_permission(user_id: str, permission: str) -> str:
    """Check whether a user holds a permission (via roles or a direct grant)."""
    return dump(auth.check_permission(user_id, permission))


@mcp.tool()
def auth_user_permissions(user_id: Optional[str] = None, identifier: Optional[str] = None) -> str:
    """The effective roles and permissions for a user (by id or email/mobile)."""
    user = auth.find_user_by_id(user_id) if user_id else auth.find_user(identifier)
    if not user:
        return dump({"error": "User not found"})
    return dump({"user_id": user.id, "name": user.name,
                 "roles": auth.user_roles(user), "permissions": auth.user_permissions(user),
                 "extra_permissions": user.extra_permissions})


@mcp.tool()
def auth_user_roles(user_id: Optional[str] = None, identifier: Optional[str] = None) -> str:
    """The roles held by a user, their primary role and their effective permissions."""
    user = auth.find_user_by_id(user_id) if user_id else auth.find_user(identifier)
    if not user:
        return dump({"error": "User not found"})
    return dump({"user_id": user.id, "name": user.name, "role": user.role,
                 "roles": auth.user_roles(user), "primary_role": auth._primary_role(user),
                 "permissions": auth.user_permissions(user)})


@mcp.tool()
def auth_users_by_role(role: str) -> str:
    """All portal users holding a given role."""
    users = auth.users_by_role(role)
    return dump({"role": role, "count": len(users), "users": users})


# ============================================================
# ============ CONSTRUCTION WING (techniques · cost · codes) ===
# ============================================================


def _construction_calculator_html() -> str:
    """A self-contained, on-page cost calculator driven by construction.py config."""
    cfg = construction.CONSTRUCTION_CONFIG
    payload = {
        "rates": cfg["quality_base_rate_sqft"], "tiers": cfg["quality_labels"],
        "types": {k: v["factor"] for k, v in construction.BUILDING_TYPES.items()},
        "type_labels": {k: v["label"] for k, v in construction.BUILDING_TYPES.items()},
        "systems": {s["key"]: s["cost_factor"] for s in construction.CONSTRUCTION_SYSTEMS},
        "system_labels": {s["key"]: s["name"] for s in construction.CONSTRUCTION_SYSTEMS},
        "cities": cfg["city_multipliers"],
        "prelim": cfg["preliminaries_pct"], "cont": cfg["contingency_pct"],
        "consult": cfg["consultancy_pct"], "op": cfg["overhead_profit_pct"],
        "floor_pct": cfg["floor_premium_pct"], "floor_from": cfg["floor_premium_from"],
    }
    sel = ("padding:6px;border:1px solid var(--line);background:var(--surface);color:var(--ink);"
           "border-radius:6px")
    return (
        '<div style="display:flex;flex-wrap:wrap;gap:12px;align-items:flex-end">'
        f'<label>Covered area (sqft)<br><input id="cc-area" type="number" value="2000" min="50" style="{sel};width:140px"></label>'
        f'<label>Floors<br><input id="cc-floors" type="number" value="2" min="1" style="{sel};width:90px"></label>'
        f'<label>Building type<br><select id="cc-type" style="{sel}"></select></label>'
        f'<label>Quality<br><select id="cc-tier" style="{sel}"></select></label>'
        f'<label>Technique<br><select id="cc-sys" style="{sel}"></select></label>'
        f'<label>City<br><select id="cc-city" style="{sel}"></select></label>'
        '</div>'
        '<h3 id="cc-out" style="margin:16px 0 4px">…</h3>'
        '<div id="cc-detail" style="color:var(--muted);font-size:13px"></div>'
        '<script>(function(){var D=' + json.dumps(payload) + ';'
        'function opt(el,obj,sel){Object.keys(obj).forEach(function(k){var o=document.createElement("option");'
        'o.value=k;o.textContent=obj[k];el.appendChild(o);});el.value=sel;}'
        'var t=document.getElementById("cc-type"),q=document.getElementById("cc-tier"),'
        's=document.getElementById("cc-sys"),c=document.getElementById("cc-city");'
        'opt(t,D.type_labels,"house");opt(q,D.tiers,"standard");opt(s,D.system_labels,"rcc_frame");'
        'opt(c,D.cities,"Lahore");'
        'function fmt(n){return "Rs "+(n/1e6).toFixed(2)+"M";}'
        'function calc(){var a=+document.getElementById("cc-area").value||0,'
        'f=+document.getElementById("cc-floors").value||1;'
        'var base=D.rates[q.value]*D.types[t.value]*(D.cities[c.value]||1)*D.systems[s.value]'
        '*(1+D.floor_pct/100*Math.max(0,f-D.floor_from));'
        'var sub=a*base,pre=sub*D.prelim/100,con=(sub+pre)*D.cont/100,cs=sub*D.consult/100,'
        'op=(sub+pre)*D.op/100,tot=sub+pre+con+cs+op;'
        'document.getElementById("cc-out").textContent=fmt(tot)+"  (Rs "+Math.round(tot/(a||1)).toLocaleString()+"/sqft)";'
        'document.getElementById("cc-detail").textContent="Construction "+fmt(sub)+" · preliminaries "+fmt(pre)'
        '+ " · contingency "+fmt(con)+" · consultancy "+fmt(cs)+" · overhead & profit "+fmt(op);}'
        '["cc-area","cc-floors"].forEach(function(id){document.getElementById(id).addEventListener("input",calc);});'
        '[t,q,s,c].forEach(function(el){el.addEventListener("change",calc);});calc();})();</script>'
    )


@mcp.tool()
def construction_overview() -> str:
    """Counts, category breakdowns and configuration for the construction wing."""
    return dump(construction.construction_overview())


@mcp.tool()
def construction_techniques(
    category: Optional[str] = None, building_type: Optional[str] = None,
    max_floors: Optional[int] = None, min_floors: Optional[int] = None,
) -> str:
    """Catalogue of construction techniques / systems (RCC frame, steel, PEB, precast,
    tunnel form, ICF, AAC, facades, roofing, green building …).

    Each carries cost factor, build speed, material/labour intensity, soil and seismic
    suitability, equipment, pros/cons, sustainability, warranty and code references.
    """
    rows = construction.construction_systems(category)
    if building_type:
        rows = [s for s in rows if building_type in s["suitable_for"]]
    if max_floors is not None:
        rows = [s for s in rows if s["min_floors"] <= max_floors <= s["max_floors"]]
    if min_floors is not None:
        rows = [s for s in rows if s["max_floors"] >= min_floors]
    return dump({"count": len(rows), "category": category, "techniques": rows,
                 "categories": sorted({s["category"] for s in construction.CONSTRUCTION_SYSTEMS})})


@mcp.tool()
def construction_technique(key: str) -> str:
    """One construction technique / system by key (e.g. ``rcc_frame``, ``peb``)."""
    row = construction.find_system(key)
    if not row:
        return dump({"error": f"Unknown technique: {key}",
                     "keys": [s["key"] for s in construction.CONSTRUCTION_SYSTEMS]})
    return dump(row)


@mcp.tool()
def construction_materials(category: Optional[str] = None) -> str:
    """Building-material catalogue with live unit rates, wastage, lead times,
    local availability, alternatives and eco-ratings."""
    rows = construction.materials(category)
    return dump({"count": len(rows), "category": category, "materials": rows,
                 "categories": sorted({m["category"] for m in construction.MATERIALS})})


@mcp.tool()
def construction_material(key: str) -> str:
    """One building material by key (e.g. ``cement_opc``, ``steel_60``)."""
    row = construction.find_material(key)
    if not row:
        return dump({"error": f"Unknown material: {key}",
                     "keys": [m["key"] for m in construction.MATERIALS]})
    return dump(row)


@mcp.tool()
def construction_element_rates() -> str:
    """BOQ element unit rates (material / labour / plant / overhead) used for rate analysis."""
    rows = []
    for key in construction.ELEMENT_RATES:
        rows.append(construction.rate_analysis(key))
    return dump({"count": len(rows), "period": "current", "elements": rows})


@mcp.tool()
def construction_rate_analysis(element: str, city: Optional[str] = None) -> str:
    """Rate analysis for one BOQ element: material, labour, plant and overhead build-up."""
    return dump(construction.rate_analysis(element, city))


@mcp.tool()
def construction_estimate(
    covered_area: float,
    floors: int = 1,
    building_type: str = "house",
    quality_tier: str = "standard",
    system: str = "rcc_frame",
    city: Optional[str] = None,
    plot_area: Optional[float] = None,
    escalation_years: float = 0.0,
) -> str:
    """Parameterised construction-cost estimate: element-wise build-up, preliminaries,
    contingency, consultancy, contractor overhead & profit, escalation, totals, cost
    per sq-ft, a phase timeline and a material take-off."""
    return dump(construction.estimate_construction(
        covered_area, floors=floors, building_type=building_type, quality_tier=quality_tier,
        system=system, city=city, plot_area=plot_area, escalation_years=escalation_years))


@mcp.tool()
def construction_timeline(
    covered_area: float, floors: int = 1, building_type: str = "house", system: str = "rcc_frame",
) -> str:
    """Phase-weighted construction timeline (mobilisation → structure → finishes → handover)."""
    return dump(construction.timeline_estimate(covered_area, floors, building_type, system))


@mcp.tool()
def construction_takeoff(
    covered_area: float, quality_tier: str = "standard", building_type: str = "house",
) -> str:
    """Indicative material take-off (cement, steel, sand, aggregate, bricks, tiles, paint …)
    from a covered area, with wastage."""
    return dump(construction.material_takeoff(covered_area, quality_tier, building_type))


@mcp.tool()
def construction_compare(
    covered_area: float, floors: int = 1, building_type: str = "house",
    quality_tier: str = "standard", city: Optional[str] = None, category: str = "structure",
) -> str:
    """Compare competing construction techniques by cost, unit rate and build speed."""
    return dump(construction.compare_systems(covered_area, floors=floors, building_type=building_type,
                                             quality_tier=quality_tier, city=city, category=category))


@mcp.tool()
def construction_impact(
    covered_area: float, building_type: str = "house", city: Optional[str] = None,
    from_tier: str = "standard", to_tier: str = "premium",
    market_rate_sqft: float = 12000.0, gross_yield: float = 0.05, floors: int = 1,
) -> str:
    """How upgrading construction quality moves market value, rent, yield and payback —
    the real-estate impact of the build choice."""
    return dump(construction.construction_impact(covered_area, building_type=building_type, city=city,
                                                 from_tier=from_tier, to_tier=to_tier,
                                                 market_rate_sqft=market_rate_sqft,
                                                 gross_yield=gross_yield, floors=floors))


@mcp.tool()
def construction_advisory(
    plot_area: float, floors: int = 2, building_type: str = "house", city: Optional[str] = None,
    soil: str = "sandy_loam", seismic_zone: str = "2A", budget_per_sqft: Optional[float] = None,
) -> str:
    """Recommend the best technique, foundation and guidelines for a site given its soil,
    seismic zone, height and budget."""
    return dump(construction.construction_advisory(
        plot_area, floors=floors, building_type=building_type, city=city, soil=soil,
        seismic_zone=seismic_zone, budget_per_sqft=budget_per_sqft))


@mcp.tool()
def construction_guidelines(
    category: Optional[str] = None, authority: Optional[str] = None, building_type: Optional[str] = None,
) -> str:
    """Building codes, byelaws and guidelines (zoning/setbacks, FAR/height, structural,
    seismic, fire, accessibility, environmental, material standards, HSE …)."""
    rows = construction.guidelines(category, authority, building_type)
    return dump({"count": len(rows), "guidelines": rows,
                 "categories": sorted({g["category"] for g in construction.CONSTRUCTION_GUIDELINES})})


@mcp.tool()
def construction_approvals(project_type: str = "house", city: Optional[str] = None) -> str:
    """The NOC / approval workflow for a project type: steps, authority, documents and
    durations."""
    return dump(construction.approval_checklist(project_type, city))


@mcp.tool()
def construction_qa(stage: Optional[str] = None) -> str:
    """Quality-assurance inspection checklists by construction stage."""
    return dump(construction.qa_checklist(stage))


@mcp.tool()
def construction_hse() -> str:
    """Health, safety & environment (HSE) rules for construction sites."""
    return dump({"count": len(construction.HSE_RULES), "rules": construction.hse_rules()})


@mcp.tool()
def construction_trades() -> str:
    """Construction trades with current daily wage rates."""
    rows = construction.trades()
    return dump({"count": len(rows), "currency": "PKR", "trades": rows})


@mcp.tool()
def construction_estimate_save(
    title: str,
    covered_area: float,
    floors: int = 1,
    building_type: str = "house",
    quality_tier: str = "standard",
    system: str = "rcc_frame",
    city: Optional[str] = None,
    plot_area: Optional[float] = None,
    escalation_years: float = 0.0,
    notes: Optional[str] = None,
) -> str:
    """Compute a construction estimate and persist it for the project book."""
    est = construction.estimate_construction(covered_area, floors=floors, building_type=building_type,
                                             quality_tier=quality_tier, system=system, city=city,
                                             plot_area=plot_area, escalation_years=escalation_years)
    if "error" in est:
        return dump(est)
    rec = construction.save_estimate(est, title, notes)
    return dump({"saved": construction.estimate_view(rec), "estimate": est})


@mcp.tool()
def construction_estimates(building_type: Optional[str] = None, city: Optional[str] = None) -> str:
    """Saved construction estimates in the project book."""
    rows = [construction.estimate_view(e) for e in construction.list_estimates(building_type, city)]
    return dump({"count": len(rows), "estimates": rows})


@mcp.tool()
def construction_estimate_get(estimate_id: str) -> str:
    """One saved construction estimate by id."""
    rec = construction.find_estimate(estimate_id)
    if not rec:
        return dump({"error": f"Unknown estimate: {estimate_id}"})
    return dump(construction.estimate_view(rec))


@mcp.tool()
def construction_portal(lang: str = "en", theme: str = "auto") -> str:
    """Render the **Construction wing** portal page (HTML) — techniques, rates, codes,
    approvals and a live cost calculator — bilingual and themed."""
    ov = construction.construction_overview()
    c = ov["counts"]
    tiers = construction.CONSTRUCTION_CONFIG["quality_base_rate_sqft"]
    tier_cards = [[f"{construction.CONSTRUCTION_CONFIG['quality_labels'][k]}",
                   f"Rs {v:,.0f}/sqft", "base turnkey rate"] for k, v in tiers.items()]
    tech_rows = [[s["name"], s["category"], f"{s['cost_factor']:.2f}x",
                  f"{s['speed_floors_per_month']}/mo", s["sustainability"], s["seismic_rating"]]
                 for s in sorted(construction.CONSTRUCTION_SYSTEMS, key=lambda x: x["cost_factor"])]
    mat_rows = [[m["name"], m["unit"], f"Rs {m['unit_rate']:,.0f}", m["availability"],
                 f"{m['lead_time_days']} d"] for m in construction.MATERIALS]
    guide_rows = [[g["title"], g["category"], g["authority"], g["code"]]
                  for g in construction.CONSTRUCTION_GUIDELINES]
    appr_rows = [[s["step"], s["name"], s["authority"], f"{s['duration_days']} d"]
                 for s in construction.approval_checklist("house")["steps"]]
    hse_rows = [[r["key"], r["rule"]] for r in construction.HSE_RULES]
    sections: List[Dict[str, Any]] = [
        {"kind": "cards", "heading": "Construction at a glance", "items": [
            ["Techniques", c["systems"], "systems & methods"],
            ["Materials", c["materials"], "with live rates"],
            ["Element rates", c["element_rates"], "BOQ line items"],
            ["Guidelines", c["guidelines"], "codes & byelaws"],
            ["Approval steps", c["approval_steps"], "NOC workflow"],
            ["Quality tiers", len(tiers), "economy → luxury"]]},
        {"kind": "text", "heading": "About this wing", "text": (
            "The construction wing brings cost analysis, estimation, technique selection, "
            "impact on real-estate value, and building codes/guidelines into one place. "
            "Every figure is produced by the same engine that powers the API and MCP tools, "
            "so estimates, comparisons and advisories are consistent everywhere.")},
        {"kind": "cards", "heading": "Quality tiers & base build rates", "items": tier_cards},
        {"kind": "html", "heading": "Interactive cost calculator", "html": _construction_calculator_html()},
        {"kind": "table", "heading": "Construction techniques & systems",
         "columns": ["System", "Category", "Cost factor", "Speed", "Sustainability", "Seismic"],
         "rows": tech_rows},
        {"kind": "table", "heading": "Key materials & current rates",
         "columns": ["Material", "Unit", "Rate", "Availability", "Lead time"], "rows": mat_rows},
        {"kind": "table", "heading": "Guidelines, codes & byelaws",
         "columns": ["Guideline", "Category", "Authority", "Code"], "rows": guide_rows},
        {"kind": "table", "heading": "Approval workflow (house)",
         "columns": ["Step", "Approval", "Authority", "Duration"], "rows": appr_rows},
        {"kind": "table", "heading": "Site safety (HSE)",
         "columns": ["Rule", "Requirement"], "rows": hse_rows},
    ]
    ads = content.ad_section(slot="banner", category="construction_technique", lang=lang)
    if ads.get("count"):
        sections.append(ads)
    return gis.build_report_html(title="Construction wing", subtitle="Techniques · cost analysis · codes & guidelines",
                                 sections=sections, ticker_html=_portal_ticker(lang), lang=lang, theme=theme)


@mcp.tool()
def construction_report(
    covered_area: float, floors: int = 1, building_type: str = "house", quality_tier: str = "standard",
    system: str = "rcc_frame", city: Optional[str] = None, lang: str = "en", theme: str = "auto",
) -> str:
    """Render a printable **construction cost report** (HTML) for one building: element
    build-up, totals, timeline, take-off and rate analysis."""
    est = construction.estimate_construction(covered_area, floors=floors, building_type=building_type,
                                             quality_tier=quality_tier, system=system, city=city)
    if "error" in est:
        return dump(est)
    cost = est["cost"]
    fees: List[Dict[str, Any]] = [
        {"kind": "cards", "heading": "Estimate summary", "items": [
            ["Total project cost", cost["total_text"], f"{covered_area:,.0f} sqft, G+{max(0, floors - 1)}"],
            ["Cost / sqft", f"Rs {cost['cost_per_sqft']:,.0f}", "turnkey incl. margin"],
            ["Construction", f"Rs {cost['subtotal_construction']:,.0f}", "structure + finishes + MEP"],
            ["Duration", f"{est['timeline']['total_days']} days", f"{est['timeline']['total_months']} months"]]},
        {"kind": "kv", "heading": "Assumptions", "items": [
            ["Quality tier", quality_tier], ["Technique", est["system"]["name"] or system],
            ["Base rate / sqft", f"Rs {est['assumptions']['base_rate_sqft']:,.0f}"],
            ["Effective rate / sqft", f"Rs {est['assumptions']['effective_rate_sqft']:,.0f}"],
            ["Building-type factor", est["assumptions"]["building_type_factor"]],
            ["City factor", est["assumptions"]["city_factor"]]]},
        {"kind": "table", "heading": "Element build-up",
         "columns": ["Element", "Category", "Share %", "Amount (PKR)"],
         "numeric": ["Share %", "Amount (PKR)"],
         "rows": [[e["label"], e["category"], e["share_pct"], e["amount"]] for e in est["elements"]]},
        {"kind": "table", "heading": "Materials take-off",
         "columns": ["Material", "Unit", "Quantity", "With wastage", "Rate", "Cost"],
         "numeric": ["Quantity", "With wastage", "Rate", "Cost"],
         "rows": [[l["name"], l["unit"], l["quantity"], l["quantity_with_wastage"],
                   l["unit_rate"], l["estimated_cost"]] for l in est["takeoff"]["lines"]]},
        {"kind": "table", "heading": "Construction timeline",
         "columns": ["Phase", "Days", "Weight %"],
         "numeric": ["Days", "Weight %"],
         "rows": [[p["name"], p["days"], p["weight_pct"]] for p in est["timeline"]["phases"]]},
    ]
    ads = content.ad_section(slot="infeed", category="materials", lang=lang)
    if ads.get("count"):
        fees.append(ads)
    return gis.build_report_html(
        title="Construction cost report",
        subtitle=f"{building_type.title()} · {covered_area:,.0f} sqft · {quality_tier}",
        sections=fees, ticker_html=_portal_ticker(lang), lang=lang, theme=theme)


@mcp.resource("construction://overview", name="Construction overview",
              description="Counts and categories across the construction wing.")
def res_construction_overview() -> str:
    return construction_overview()


@mcp.resource("construction://techniques", name="Construction techniques",
              description="Catalogue of construction systems and methods.")
def res_construction_techniques() -> str:
    return construction_techniques()


@mcp.resource("construction://technique/{key}", name="Construction technique",
              description="One construction technique by key.")
def res_construction_technique(key: str) -> str:
    return construction_technique(key)


@mcp.resource("construction://materials", name="Building materials",
              description="Material catalogue with unit rates and availability.")
def res_construction_materials() -> str:
    return construction_materials()


@mcp.resource("construction://element-rates", name="Element rates",
              description="BOQ element unit rates for rate analysis.")
def res_construction_element_rates() -> str:
    return construction_element_rates()


@mcp.resource("construction://guidelines", name="Construction guidelines",
              description="Building codes, byelaws and guidelines.")
def res_construction_guidelines() -> str:
    return construction_guidelines()


@mcp.resource("construction://approvals", name="Approval workflow",
              description="NOC / approval steps for a project.")
def res_construction_approvals() -> str:
    return construction_approvals()


@mcp.resource("construction://trades", name="Construction trades",
              description="Trades and daily wage rates.")
def res_construction_trades() -> str:
    return construction_trades()


@mcp.prompt(name="construction_estimate_prompt",
            description="Prepare a construction cost estimate for a building.")
def prompt_construction_estimate(building_type: str = "house", covered_area: str = "2000",
                                 floors: str = "2", city: str = "Lahore") -> str:
    return (
        "You are a construction cost consultant in Pakistan.\n"
        f"Building: {building_type}, covered area {covered_area} sqft, {floors} floors, city {city}.\n"
        "1. Use construction_techniques to shortlist 2–3 suitable systems.\n"
        "2. Run construction_estimate for each at standard and premium tiers.\n"
        "3. Use construction_takeoff for the material quantities and construction_timeline for the plan.\n"
        "4. Recommend a technique with a cost/speed/quality trade-off, and note the key guidelines."
    )


@mcp.prompt(name="construction_advisory_prompt",
            description="Advise on technique, foundation and codes for a site.")
def prompt_construction_advisory(plot_area: str = "2722", city: str = "Lahore",
                                 soil: str = "sandy_loam", seismic_zone: str = "2A") -> str:
    return (
        "You are a structural/construction advisor.\n"
        f"Site: {plot_area} sqft in {city}; soil {soil}; seismic zone {seismic_zone}.\n"
        "1. Call construction_advisory for the recommended system and foundation.\n"
        "2. Call construction_guidelines to list the applicable codes and byelaws.\n"
        "3. Call construction_approvals for the NOC/approval workflow.\n"
        "4. Give a prioritised build plan with the risks to watch."
    )


# ============================================================
# ============ MAINTENANCE WING (services · lifecycle) =========
# ============================================================


def _maintenance_calculator_html() -> str:
    """A self-contained, on-page annual-maintenance cost calculator."""
    cfg = maintenance.MAINTENANCE_CONFIG
    payload = {
        "rates": maintenance.PROPERTY_MAINTENANCE_RATES,
        "type_labels": {k: k.replace("-", " ").title() for k in maintenance.PROPERTY_MAINTENANCE_RATES},
        "tiers": {k: v["multiplier"] for k, v in maintenance.MAINTENANCE_TIERS.items()},
        "tier_labels": {k: v["label"] for k, v in maintenance.MAINTENANCE_TIERS.items()},
        "cities": cfg["city_multipliers"], "age_pct": cfg["age_factor_pct_per_year"],
        "age_grace": cfg["age_grace_years"], "age_cap": cfg["age_factor_cap"],
    }
    sel = ("padding:6px;border:1px solid var(--line);background:var(--surface);color:var(--ink);"
           "border-radius:6px")
    return (
        '<div style="display:flex;flex-wrap:wrap;gap:12px;align-items:flex-end">'
        f'<label>Covered area (sqft)<br><input id="mc-area" type="number" value="2000" min="50" style="{sel};width:140px"></label>'
        f'<label>Age (years)<br><input id="mc-age" type="number" value="8" min="0" style="{sel};width:100px"></label>'
        f'<label>Property type<br><select id="mc-type" style="{sel}"></select></label>'
        f'<label>AMC tier<br><select id="mc-tier" style="{sel}"></select></label>'
        f'<label>City<br><select id="mc-city" style="{sel}"></select></label>'
        '</div>'
        '<h3 id="mc-out" style="margin:16px 0 4px">…</h3>'
        '<div id="mc-detail" style="color:var(--muted);font-size:13px"></div>'
        '<script>(function(){var D=' + json.dumps(payload) + ';'
        'function opt(el,obj,sel){Object.keys(obj).forEach(function(k){var o=document.createElement("option");'
        'o.value=k;o.textContent=obj[k];el.appendChild(o);});el.value=sel;}'
        'var t=document.getElementById("mc-type"),q=document.getElementById("mc-tier"),c=document.getElementById("mc-city");'
        'opt(t,D.type_labels,"house");opt(q,D.tier_labels,"standard");opt(c,D.cities,"Lahore");'
        'function fmt(n){return "Rs "+(n/1e6).toFixed(2)+"M";}'
        'function calc(){var a=+document.getElementById("mc-area").value||0,'
        'age=+document.getElementById("mc-age").value||0;'
        'var rate=D.rates[t.value].standard*(D.cities[c.value]||1)*D.tiers[q.value]'
        '*Math.min(D.age_cap,1+D.age_pct/100*Math.max(0,age-D.age_grace));'
        'var annual=a*rate;'
        'document.getElementById("mc-out").textContent=fmt(annual)+" / year  (Rs "+Math.round(rate).toLocaleString()+"/sqft·yr)";'
        'document.getElementById("mc-detail").textContent="Monthly "+fmt(annual/12)+" · routine maintenance only"'
        '+ " (capital replacement reserve is separate)";}'
        '["mc-area","mc-age"].forEach(function(id){document.getElementById(id).addEventListener("input",calc);});'
        '[t,q,c].forEach(function(el){el.addEventListener("change",calc);});calc();})();</script>'
    )


@mcp.tool()
def maintenance_overview() -> str:
    """Counts, category breakdowns and configuration for the maintenance wing."""
    return dump(maintenance.maintenance_overview())


@mcp.tool()
def maintenance_components(category: Optional[str] = None) -> str:
    """Maintainable building components with service life, replacement cost, criticality,
    inspection frequency and periodic tasks."""
    rows = maintenance.components(category)
    return dump({"count": len(rows), "category": category, "components": rows,
                 "categories": maintenance.ASSET_CATEGORIES})


@mcp.tool()
def maintenance_component(key: str) -> str:
    """One asset component by key (e.g. ``roof_waterproofing``, ``hvac``)."""
    row = maintenance.find_component(key)
    if not row:
        return dump({"error": f"Unknown component: {key}",
                     "keys": [c["key"] for c in maintenance.ASSET_COMPONENTS]})
    return dump(row)


@mcp.tool()
def maintenance_services(category: Optional[str] = None, emergency: Optional[bool] = None) -> str:
    """Maintenance services & trades with unit cost bands, emergency flags and response
    times."""
    rows = maintenance.services(category, emergency)
    return dump({"count": len(rows), "services": rows,
                 "categories": sorted({s["category"] for s in maintenance.MAINTENANCE_SERVICES})})


@mcp.tool()
def maintenance_service(key: str) -> str:
    """One maintenance service by key (e.g. ``ac_service``, ``waterproofing``)."""
    row = maintenance.find_service(key)
    if not row:
        return dump({"error": f"Unknown service: {key}",
                     "keys": [s["key"] for s in maintenance.MAINTENANCE_SERVICES]})
    return dump(row)


@mcp.tool()
def maintenance_defects(category: Optional[str] = None, severity: Optional[str] = None,
                        component: Optional[str] = None) -> str:
    """Defect catalogue: symptoms, causes, severity, diagnosis, repair method, cost band,
    urgency and prevention."""
    rows = maintenance.defects(category, severity, component)
    return dump({"count": len(rows), "defects": rows,
                 "categories": sorted({d["category"] for d in maintenance.DEFECT_CATALOGUE})})


@mcp.tool()
def maintenance_defect(key: str) -> str:
    """One defect by key (e.g. ``roof_seepage``, ``structural_cracks``)."""
    row = maintenance.find_defect(key)
    if not row:
        return dump({"error": f"Unknown defect: {key}",
                     "keys": [d["key"] for d in maintenance.DEFECT_CATALOGUE]})
    return dump(row)


@mcp.tool()
def maintenance_estimate(
    covered_area: float, property_type: str = "house", tier: str = "standard",
    quality: str = "standard", age_years: float = 0.0, city: Optional[str] = None, floors: int = 1,
) -> str:
    """Annual routine-maintenance cost estimate with a category breakdown and the
    capital-replacement reserve."""
    return dump(maintenance.estimate_maintenance(
        covered_area, property_type=property_type, tier=tier, quality=quality,
        age_years=age_years, city=city, floors=floors))


@mcp.tool()
def maintenance_schedule(property_type: str = "house", age_years: float = 0.0,
                         horizon_months: int = 12) -> str:
    """A periodic preventive-maintenance calendar for a property."""
    return dump(maintenance.preventive_schedule(property_type, age_years, horizon_months))


@mcp.tool()
def maintenance_lifecycle(covered_area: float, property_type: str = "house", quality: str = "standard",
                          age_years: float = 0.0, city: Optional[str] = None, years: int = 30) -> str:
    """Multi-year capital-replacement schedule (a reserve study) with inflated costs."""
    return dump(maintenance.lifecycle_plan(covered_area, property_type=property_type, quality=quality,
                                           age_years=age_years, city=city, years=years))


@mcp.tool()
def maintenance_reserve(covered_area: float, property_type: str = "house", quality: str = "standard",
                        age_years: float = 0.0, city: Optional[str] = None) -> str:
    """Annual sinking-fund (reserve) contribution to replace components at end of life."""
    return dump(maintenance.lifecycle_reserve(covered_area, property_type=property_type, quality=quality,
                                              age_years=age_years, city=city))


@mcp.tool()
def maintenance_condition(age_years: float, property_type: str = "house",
                          ratings: Optional[Dict[str, int]] = None) -> str:
    """Score a building's condition (1–5 per area) into a band with recommended actions."""
    return dump(maintenance.condition_assessment(age_years, ratings, property_type))


@mcp.tool()
def maintenance_repair_estimate(defect: str, quantity: float = 1.0, city: Optional[str] = None) -> str:
    """Estimate the cost to repair a known defect over a given quantity."""
    return dump(maintenance.repair_estimate(defect, quantity, city))


@mcp.tool()
def maintenance_repair_or_replace(
    component: str, age_years: float, condition: Optional[str] = None,
    covered_area: float = 1000.0, quality: str = "standard", city: Optional[str] = None,
) -> str:
    """Decide between repairing and replacing a component, with a 5-year cost comparison."""
    return dump(maintenance.repair_or_replace(component, age_years, condition=condition,
                                              covered_area=covered_area, quality=quality, city=city))


@mcp.tool()
def maintenance_impact(
    market_value: float, monthly_rent: float, covered_area: float = 1000.0,
    current_condition: str = "fair", tier: str = "standard",
) -> str:
    """How condition and maintenance move market value, rent, yield, occupancy and tenant
    retention."""
    return dump(maintenance.maintenance_impact(market_value, monthly_rent, covered_area,
                                               current_condition, tier))


@mcp.tool()
def maintenance_guidelines(category: Optional[str] = None) -> str:
    """Maintenance best-practice, compliance, safety and management guidelines."""
    rows = maintenance.guidelines(category)
    return dump({"count": len(rows), "guidelines": rows,
                 "categories": sorted({g["category"] for g in maintenance.MAINTENANCE_GUIDELINES})})


@mcp.tool()
def maintenance_warranty(component: Optional[str] = None) -> str:
    """Warranty terms by component (duration, cover and exclusions)."""
    return dump(maintenance.warranty(component))


@mcp.tool()
def maintenance_inspection(area: Optional[str] = None) -> str:
    """Inspection checklists by area (structural, envelope, MEP, finishes, safety)."""
    return dump(maintenance.inspection_checklist(area))


@mcp.tool()
def maintenance_plan_save(
    title: str, covered_area: float, property_type: str = "house", tier: str = "standard",
    quality: str = "standard", age_years: float = 0.0, city: Optional[str] = None, notes: Optional[str] = None,
) -> str:
    """Compute an annual-maintenance estimate and persist it as a maintenance plan."""
    est = maintenance.estimate_maintenance(covered_area, property_type=property_type, tier=tier,
                                           quality=quality, age_years=age_years, city=city)
    if "error" in est:
        return dump(est)
    est["condition_band"] = maintenance.condition_assessment(age_years, property_type=property_type)["band"]
    rec = maintenance.save_plan(est, title, notes)
    return dump({"saved": maintenance.plan_view(rec), "estimate": est})


@mcp.tool()
def maintenance_plans(property_type: Optional[str] = None) -> str:
    """Saved maintenance plans."""
    rows = [maintenance.plan_view(p) for p in maintenance.list_plans(property_type)]
    return dump({"count": len(rows), "plans": rows})


@mcp.tool()
def maintenance_plan_get(plan_id: str) -> str:
    """One saved maintenance plan by id."""
    rec = maintenance.find_plan(plan_id)
    if not rec:
        return dump({"error": f"Unknown plan: {plan_id}"})
    return dump(maintenance.plan_view(rec))


@mcp.tool()
def maintenance_work_order_create(
    title: str, property_type: str = "house", component: Optional[str] = None,
    defect: Optional[str] = None, priority: str = "routine", description: Optional[str] = None,
    estimated_cost: float = 0.0, assignee: Optional[str] = None,
) -> str:
    """Raise a maintenance work order (a service request / job)."""
    rec = maintenance.WorkOrder(title=title, property_type=property_type, component=component,
                                defect=defect, priority=priority, description=description,
                                estimated_cost=estimated_cost, assignee=assignee)
    maintenance.work_orders_db.append(rec)
    return dump(maintenance.work_order_view(rec))


@mcp.tool()
def maintenance_work_orders(status: Optional[str] = None, priority: Optional[str] = None,
                            component: Optional[str] = None) -> str:
    """List maintenance work orders, filtered by status / priority / component."""
    rows = [maintenance.work_order_view(w) for w in maintenance.list_work_orders(status, priority, component)]
    return dump({"count": len(rows), "work_orders": rows})


@mcp.tool()
def maintenance_work_order_get(wo_id: str) -> str:
    """One maintenance work order by id."""
    rec = maintenance.find_work_order(wo_id)
    if not rec:
        return dump({"error": f"Unknown work order: {wo_id}"})
    return dump(maintenance.work_order_view(rec))


@mcp.tool()
def maintenance_work_order_update(
    wo_id: str, status: Optional[str] = None, priority: Optional[str] = None,
    assignee: Optional[str] = None, estimated_cost: Optional[float] = None,
    description: Optional[str] = None,
) -> str:
    """Update a maintenance work order (status, priority, assignee, cost)."""
    rec = maintenance.find_work_order(wo_id)
    if not rec:
        return dump({"error": f"Unknown work order: {wo_id}"})
    if status is not None:
        rec.status = status
    if priority is not None:
        rec.priority = priority
    if assignee is not None:
        rec.assignee = assignee
    if estimated_cost is not None:
        rec.estimated_cost = estimated_cost
    if description is not None:
        rec.description = description
    return dump(maintenance.work_order_view(rec))


@mcp.tool()
def maintenance_portal(lang: str = "en", theme: str = "auto") -> str:
    """Render the **Maintenance wing** portal page (HTML) — components, services, defects,
    cost tables, AMC tiers and a live maintenance-cost calculator — bilingual and themed."""
    ov = maintenance.maintenance_overview()
    c = ov["counts"]
    comp_rows = [[x["name"], x["category"], f"{x['service_life_years']} y",
                  f"{x['replacement_pct']*100:.1f}%", x["criticality"], x["frequency"]]
                 for x in maintenance.ASSET_COMPONENTS]
    svc_rows = [[s["name"], s["category"], s["unit"], f"Rs {s['cost_low']:,}–{s['cost_high']:,}",
                 "yes" if s["emergency"] else "no", f"{s['response_hours']} h"]
                for s in maintenance.MAINTENANCE_SERVICES]
    defect_rows = [[d["name"], d["category"], d["severity"], d["urgency"], d["repair"]]
                   for d in maintenance.DEFECT_CATALOGUE]
    rate_rows = [[pt, f"Rs {r['basic']:,.0f}", f"Rs {r['standard']:,.0f}", f"Rs {r['premium']:,.0f}"]
                 for pt, r in maintenance.PROPERTY_MAINTENANCE_RATES.items()]
    tier_rows = [[t["label"], f"{t['multiplier']:.2f}x", "; ".join(t["includes"])]
                 for t in maintenance.MAINTENANCE_TIERS.values()]
    guide_rows = [[g["title"], g["category"], g["summary"]] for g in maintenance.MAINTENANCE_GUIDELINES]
    sections: List[Dict[str, Any]] = [
        {"kind": "cards", "heading": "Maintenance at a glance", "items": [
            ["Components", c["components"], "maintainable assets"],
            ["Services", c["services"], "trades & vendors"],
            ["Defects", c["defects"], "in the catalogue"],
            ["Guidelines", c["guidelines"], "best practice"],
            ["AMC tiers", c["tiers"], "basic → comprehensive"],
            ["Work orders", c["work_orders"], "service requests"]]},
        {"kind": "text", "heading": "About this wing", "text": (
            "The maintenance wing covers the whole lifecycle of a building after handover: "
            "preventive schedules, condition assessment, repair versus replacement, annual "
            "cost and reserve studies, service providers, defect diagnosis and the impact of "
            "maintenance on value, rent, yield and occupancy. Estimates come from the same "
            "engine exposed over the API and MCP.")},
        {"kind": "cards", "heading": "AMC tiers", "items": [
            ["Basic", "1.00x", "on-call response, 2 visits a year"],
            ["Standard", "1.30x", "scheduled preventive + 24 h response"],
            ["Comprehensive", "1.70x", "parts included, 4 h response, uptime guarantee"]]},
        {"kind": "html", "heading": "Interactive maintenance-cost calculator",
         "html": _maintenance_calculator_html()},
        {"kind": "table", "heading": "Maintainable components",
         "columns": ["Component", "Category", "Service life", "Replacement", "Criticality", "Frequency"],
         "rows": comp_rows},
        {"kind": "table", "heading": "Maintenance services & rates",
         "columns": ["Service", "Category", "Unit", "Cost band", "Emergency", "Response"],
         "rows": svc_rows},
        {"kind": "table", "heading": "Annual maintenance rates (PKR / sqft / year)",
         "columns": ["Property type", "Basic", "Standard", "Premium"], "rows": rate_rows},
        {"kind": "table", "heading": "Defect catalogue",
         "columns": ["Defect", "Category", "Severity", "Urgency", "Repair"], "rows": defect_rows},
        {"kind": "table", "heading": "AMC tiers",
         "columns": ["Tier", "Multiplier", "Includes"], "rows": tier_rows},
        {"kind": "table", "heading": "Maintenance guidelines",
         "columns": ["Guideline", "Category", "Summary"], "rows": guide_rows},
    ]
    ads = content.ad_section(slot="sidebar", category="services", lang=lang)
    if ads.get("count"):
        sections.append(ads)
    return gis.build_report_html(title="Maintenance wing", subtitle="Services · lifecycle · condition · cost",
                                 sections=sections, ticker_html=_portal_ticker(lang), lang=lang, theme=theme)


@mcp.tool()
def maintenance_report(
    covered_area: float, property_type: str = "house", tier: str = "standard",
    quality: str = "standard", age_years: float = 0.0, city: Optional[str] = None,
    lang: str = "en", theme: str = "auto",
) -> str:
    """Render a printable **maintenance report** (HTML): annual cost, reserve, preventive
    schedule, lifecycle plan and condition assessment."""
    est = maintenance.estimate_maintenance(covered_area, property_type=property_type, tier=tier,
                                           quality=quality, age_years=age_years, city=city)
    if "error" in est:
        return dump(est)
    reserve = est["reserve"]
    cond = maintenance.condition_assessment(age_years, property_type=property_type)
    plan = maintenance.lifecycle_plan(covered_area, property_type=property_type, quality=quality,
                                      age_years=age_years, city=city, years=15)
    schedule = maintenance.preventive_schedule(property_type, age_years, 12)
    sections: List[Dict[str, Any]] = [
        {"kind": "cards", "heading": "Maintenance summary", "items": [
            ["Annual cost", est["annual"]["total_text"], f"Rs {est['annual']['per_sqft_year']:,.0f}/sqft·yr"],
            ["Monthly", est["annual"]["monthly_text"], tier + " AMC"],
            ["Reserve / year", maintenance.format_pkr(reserve["annual_reserve"]), "capital replacement"],
            ["Condition", cond["band_label"], f"score {cond['score']}/5"],
            ["15-yr replacement", maintenance.format_pkr(plan["total_replacement_cost"]), "today's values, inflated"]]},
        {"kind": "table", "heading": "Annual cost by category",
         "columns": ["Category", "Share %", "Annual cost"],
         "numeric": ["Share %", "Annual cost"],
         "rows": [[b["category"], b["share_pct"], b["annual_cost"]] for b in est["category_breakdown"]]},
        {"kind": "table", "heading": "Preventive schedule (12 months)",
         "columns": ["Component", "Month", "Frequency", "Criticality"],
         "numeric": ["Month"],
         "rows": [[t["name"], t["month"], t["frequency"], t["criticality"]] for t in schedule["tasks"]]},
        {"kind": "table", "heading": "Capital replacements (15 years)",
         "columns": ["Year", "Component", "Cost"], "numeric": ["Year", "Cost"],
         "rows": [[r["year"], r["name"], r["cost"]] for r in plan["replacements"]]},
    ]
    ads = content.ad_section(slot="infeed", category="services", lang=lang)
    if ads.get("count"):
        sections.append(ads)
    return gis.build_report_html(
        title="Maintenance report",
        subtitle=f"{property_type.title()} · {covered_area:,.0f} sqft · age {age_years:g} y · {tier}",
        sections=sections, ticker_html=_portal_ticker(lang), lang=lang, theme=theme)


@mcp.resource("maintenance://overview", name="Maintenance overview",
              description="Counts and categories across the maintenance wing.")
def res_maintenance_overview() -> str:
    return maintenance_overview()


@mcp.resource("maintenance://components", name="Maintainable components",
              description="Asset components with service life and criticality.")
def res_maintenance_components() -> str:
    return maintenance_components()


@mcp.resource("maintenance://component/{key}", name="Component",
              description="One maintainable component by key.")
def res_maintenance_component(key: str) -> str:
    return maintenance_component(key)


@mcp.resource("maintenance://services", name="Maintenance services",
              description="Maintenance services and trades with rates.")
def res_maintenance_services() -> str:
    return maintenance_services()


@mcp.resource("maintenance://defects", name="Defect catalogue",
              description="Building defects with causes, repair and prevention.")
def res_maintenance_defects() -> str:
    return maintenance_defects()


@mcp.resource("maintenance://defect/{key}", name="Defect",
              description="One defect by key.")
def res_maintenance_defect(key: str) -> str:
    return maintenance_defect(key)


@mcp.resource("maintenance://guidelines", name="Maintenance guidelines",
              description="Maintenance best-practice, compliance and safety guidelines.")
def res_maintenance_guidelines() -> str:
    return maintenance_guidelines()


@mcp.resource("maintenance://warranty", name="Warranty terms",
              description="Warranty duration, cover and exclusions by component.")
def res_maintenance_warranty() -> str:
    return maintenance_warranty()


@mcp.resource("maintenance://condition-scale", name="Condition scale",
              description="The 1–5 condition rating scale with actions.")
def res_maintenance_condition_scale() -> str:
    return dump({"scale": maintenance.CONDITION_SCALE})


@mcp.prompt(name="maintenance_plan_prompt",
            description="Prepare a maintenance plan and reserve study for a property.")
def prompt_maintenance_plan(property_type: str = "apartment", covered_area: str = "2000",
                            age_years: str = "8", city: str = "Lahore") -> str:
    return (
        "You are a facilities-management consultant in Pakistan.\n"
        f"Property: {property_type}, {covered_area} sqft, age {age_years} years, {city}.\n"
        "1. Call maintenance_estimate for the annual routine cost and reserve.\n"
        "2. Call maintenance_schedule for the 12-month preventive calendar.\n"
        "3. Call maintenance_lifecycle for the multi-year capital plan.\n"
        "4. Call maintenance_condition and maintenance_guidelines, then recommend an AMC tier."
    )


@mcp.prompt(name="maintenance_incident_prompt",
            description="Diagnose a building defect and plan the repair.")
def prompt_maintenance_incident(symptom: str = "damp patch on ceiling after rain",
                                property_type: str = "house") -> str:
    return (
        "You are a building-maintenance engineer.\n"
        f"Reported symptom: '{symptom}' in a {property_type}.\n"
        "1. Call maintenance_defects to match the symptom to a defect and its causes.\n"
        "2. Call maintenance_defect for the diagnosis and repair method.\n"
        "3. Call maintenance_repair_estimate for the cost and maintenance_repair_or_replace "
        "if a component is involved.\n"
        "4. Give a prioritised action plan with prevention measures and a work-order priority."
    )


# ============================================================
# ============ TOOLS & UTILITIES WING (calculators · GIS) ======
# ====== georeferencing · CAD · phototools · documents =========
# ====== Pakistan & Islamic calendar · reports/export ==========
# ============================================================
#
# The Tools Center turns the portal into a professional utility suite. Every
# tool is a pure-Python function in `tools.py` (standard library only), reusing
# `accounting` (mortgage/ROI), `construction` (build cost) and `gis` (measure,
# GeoJSON/KML, maps), and is exposed over MCP here and over REST in api.py.


def _tools_center_html() -> str:
    """A searchable, category-filtered grid of tool cards for the Tools Center."""
    cards = [
        {"key": t["key"], "name": t["name"], "category": t["category"],
         "cat_label": tools.TOOL_CATEGORIES.get(t["category"], t["category"]),
         "phase": t["phase"], "blurb": t["blurb"], "tool": t["mcp_tool"]}
        for t in tools.TOOL_CATALOG
    ]
    cats = [{"key": "all", "label": "All Tools"}] + [
        {"key": c["key"], "label": c["label"]} for c in tools.tool_categories()["categories"]
    ]
    sel = ("padding:6px 10px;border:1px solid var(--line);background:var(--surface);"
           "color:var(--ink);border-radius:6px")
    return (
        '<div style="display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:14px">'
        f'<input id="tc-search" placeholder="Search tools…" style="{sel};min-width:240px">'
        '<span id="tc-cats" style="display:inline-flex;flex-wrap:wrap;gap:6px"></span>'
        '</div>'
        '<div id="tc-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));'
        'gap:12px"></div>'
        '<div id="tc-empty" style="display:none;color:var(--muted);padding:12px">No tools match.</div>'
        '<p style="color:var(--muted);font-size:12px;margin-top:12px">Every card maps to an MCP tool and '
        'a matching REST endpoint — one engine powers both. Phase shows the roadmap launch order '
        '(1 = quick win, 2 = GIS workspace, 3 = professional/AI).</p>'
        '<script>(function(){var T=' + json.dumps(cards) + ',C=' + json.dumps(cats) + ';'
        'var grid=document.getElementById("tc-grid"),empty=document.getElementById("tc-empty");'
        'var search=document.getElementById("tc-search");var active="all";'
        'function card(x){var d=document.createElement("div");'
        'd.style.cssText="border:1px solid var(--line);border-radius:10px;padding:12px;background:var(--surface)";'
        'd.innerHTML="<div style=\\"font-weight:700;margin-bottom:4px\\">"+x.name+"</div>"'
        '+ "<div style=\\"color:var(--muted);font-size:12px;min-height:34px\\">"+x.blurb+"</div>"'
        '+ "<div style=\\"margin-top:8px;font-size:11px;color:var(--muted)\\">"+x.cat_label+" · phase "+x.phase+"</div>"'
        '+ "<code style=\\"font-size:11px\\">"+x.tool+"</code>";return d;}'
        'function render(){var q=search.value.toLowerCase();grid.innerHTML="";var n=0;'
        'T.forEach(function(x){if(active!=="all"&&x.category!==active)return;'
        'if(q&&(x.name+" "+x.blurb).toLowerCase().indexOf(q)<0)return;grid.appendChild(card(x));n++;});'
        'empty.style.display=n?"none":"block";}'
        'var bar=document.getElementById("tc-cats");C.forEach(function(c,i){var b=document.createElement("button");'
        'b.textContent=c.label+" ("+(c.key==="all"?T.length:T.filter(function(x){return x.category===c.key;}).length)+")";'
        'b.style.cssText="cursor:pointer;padding:6px 10px;border-radius:999px;border:1px solid var(--line);'
        'background:var(--surface);color:var(--ink);font-size:12px";if(i===0){active="all";b.style.fontWeight="700";}'
        'b.onclick=function(){active=c.key;render();};bar.appendChild(b);});'
        'search.addEventListener("input",render);render();})();</script>'
    )


def _tools_calculator_html() -> str:
    """A self-contained area converter + mortgage quick-calculator."""
    payload = {"units": tools.AREA_UNITS,
               "sqft_per": {u: tools._sqft_per(u) for u in tools.AREA_UNITS},
               "marla_standards": {k: v["marla_sqft"] for k, v in tools.MARLA_STANDARDS.items()}}
    sel = ("padding:6px;border:1px solid var(--line);background:var(--surface);color:var(--ink);"
           "border-radius:6px")
    return (
        '<div style="display:flex;flex-wrap:wrap;gap:12px;align-items:flex-end">'
        f'<label>Area value<br><input id="tc-val" type="number" value="10" min="0" style="{sel};width:120px"></label>'
        f'<label>From unit<br><select id="tc-from" style="{sel}"></select></label>'
        f'<label>Marla standard<br><select id="tc-std" style="{sel}"></select></label>'
        '</div>'
        '<h3 id="tc-areal" style="margin:14px 0 2px">…</h3>'
        '<div id="tc-aread" style="color:var(--muted);font-size:13px"></div>'
        '<hr style="border:none;border-top:1px solid var(--line);margin:18px 0">'
        '<div style="display:flex;flex-wrap:wrap;gap:12px;align-items:flex-end">'
        f'<label>Price (PKR)<br><input id="tc-price" type="number" value="10000000" min="0" style="{sel};width:150px"></label>'
        f'<label>Down payment<br><input id="tc-down" type="number" value="2000000" min="0" style="{sel};width:140px"></label>'
        f'<label>Rate %/yr<br><input id="tc-rate" type="number" value="12" step="0.1" style="{sel};width:100px"></label>'
        f'<label>Years<br><input id="tc-years" type="number" value="15" min="1" style="{sel};width:90px"></label>'
        '</div>'
        '<h3 id="tc-mort" style="margin:14px 0 2px">…</h3>'
        '<div id="tc-mortd" style="color:var(--muted);font-size:13px"></div>'
        '<script>(function(){var D=' + json.dumps(payload) + ';'
        'function opt(el,obj,sel){Object.keys(obj).forEach(function(k){var o=document.createElement("option");'
        'o.value=k;o.textContent=k;el.appendChild(o);});el.value=sel;}'
        'var f=document.getElementById("tc-from"),s=document.getElementById("tc-std");'
        'opt(f,D.units,"marla");opt(s,{standard:"standard (272.25)",small:"small (225)"},"standard");'
        'function fmt(n){return (Math.round(n*1000)/1000).toLocaleString();}'
        'function area(){var v=+document.getElementById("tc-val").value||0;'
        'var m=D.marla_standards[s.value==="small"?"small":"standard"];'
        'var per=Object.assign({},D.sqft_per,{marla:m,kanal:m*20});'
        'var sqft=v*per[f.value];var parts=[];D.units.forEach(function(u){parts.push(u+" "+fmt(sqft/per[u]));});'
        'document.getElementById("tc-areal").textContent=sqft.toLocaleString()+" sqft";'
        'document.getElementById("tc-aread").textContent=parts.join("  ·  ");}'
        'function mort(){var p=+document.getElementById("tc-price").value||0,'
        'd=+document.getElementById("tc-down").value||0,r=(+document.getElementById("tc-rate").value||0)/100,'
        'y=+document.getElementById("tc-years").value||1;var L=Math.max(0,p-d),n=y*12,i=r/12;'
        'var pay=i?L*i/(1-Math.pow(1+i,-n)):L/n;var total=pay*n;'
        'document.getElementById("tc-mort").textContent="Rs "+Math.round(pay).toLocaleString()+" / month";'
        'document.getElementById("tc-mortd").textContent="Loan "+Math.round(L).toLocaleString()+"  ·  total interest "+'
        'Math.round(total-L).toLocaleString()+"  ·  total paid "+Math.round(total).toLocaleString();}'
        '["tc-val","tc-from","tc-std"].forEach(function(id){var e=document.getElementById(id);'
        'e.addEventListener("input",area);e.addEventListener("change",area);});'
        '["tc-price","tc-down","tc-rate","tc-years"].forEach(function(id){document.getElementById(id).addEventListener("input",mort);});'
        'area();mort();})();</script>'
    )


# ---------- Calculators ----------


@mcp.tool()
def tool_area_units() -> str:
    """Area units and marla standards supported by the converters."""
    return dump(tools.area_units())


@mcp.tool()
def tool_area_convert(value: float, from_unit: str = "sqft", to_unit: str = "marla",
                      marla_sqft: float = 272.25) -> str:
    """Convert between sqft / sqyd / sqm / marla / kanal / acre / hectare."""
    return dump(tools.convert_area(value, from_unit, to_unit, marla_sqft))


@mcp.tool()
def tool_area_table(value: float, from_unit: str = "sqft", marla_sqft: float = 272.25) -> str:
    """Show an area in every supported unit at once."""
    return dump(tools.convert_area_all(value, from_unit, marla_sqft))


@mcp.tool()
def tool_length_convert(value: float, from_unit: str = "ft", to_unit: str = "m") -> str:
    """Convert between feet, inches, yards, metres, centimetres and kilometres."""
    return dump(tools.convert_length(value, from_unit, to_unit))


@mcp.tool()
def tool_plot_dimensions(area: float, from_unit: str = "marla", ratio: float = 2.0,
                         marla_sqft: float = 272.25) -> str:
    """Length / width / perimeter / diagonal of a rectangular plot from its area."""
    return dump(tools.plot_dimensions(area, from_unit, ratio, marla_sqft))


@mcp.tool()
def tool_mortgage_calculator(price: float, down_payment: float = 0.0,
                             annual_rate: Optional[float] = None, years: Optional[int] = None,
                             payments_per_year: int = 12) -> str:
    """Home-loan monthly installment, total interest and full amortisation schedule."""
    return dump(tools.mortgage_calculator(price, down_payment, annual_rate, years, payments_per_year))


@mcp.tool()
def tool_installment_plan(price: float, down_payment: float = 0.0, months: int = 36,
                          annual_markup: float = 0.0) -> str:
    """Developer-style installment plan: down payment, markup and monthly amount."""
    return dump(tools.installment_plan(price, down_payment, months, annual_markup))


@mcp.tool()
def tool_rental_yield(price: float, monthly_rent: float, annual_costs: float = 0.0,
                      vacancy_rate: float = 0.0) -> str:
    """Gross and net rental yield with payback period and cap rate."""
    return dump(tools.rental_yield(price, monthly_rent, annual_costs, vacancy_rate))


@mcp.tool()
def tool_appreciation(current_value: float, cagr: float = 0.08, years: int = 10,
                      monthly_rent: float = 0.0, rent_growth: float = 0.05) -> str:
    """Property appreciation and investment-growth projection with scenario bands."""
    return dump(tools.appreciation_projection(current_value, cagr, years, monthly_rent, rent_growth))


@mcp.tool()
def tool_price_per_unit(price: float, area: float, from_unit: str = "sqft",
                        marla_sqft: float = 272.25) -> str:
    """Price per sqft / sqyd / sqm / marla for a listing."""
    return dump(tools.price_per_unit(price, area, from_unit, marla_sqft))


@mcp.tool()
def tool_transfer_costs(price: float, province: str = "punjab", filer: bool = True,
                        rate_overrides: Optional[Dict[str, float]] = None) -> str:
    """Stamp duty, CVT, registration, mutation and withholding on a property transfer."""
    return dump(tools.transfer_costs(price, province, filer, rate_overrides))


@mcp.tool()
def tool_agent_commission(price: float, rate: Optional[float] = None, include_vat: bool = True) -> str:
    """Agent commission on a sale, with optional output VAT."""
    return dump(tools.agent_commission(price, rate, include_vat))


@mcp.tool()
def tool_capital_gains_tax(gain: float, holding_years: float, filer: bool = True) -> str:
    """Capital-gains tax on a disposal, by holding period and filer status."""
    return dump(tools.capital_gains_tax(gain, holding_years, filer))


@mcp.tool()
def tool_joint_investment(partners: List[Dict[str, Any]], total_profit: float,
                          months: float = 12.0) -> str:
    """Split a profit between partners pro-rata to capital, with each partner's ROI."""
    return dump(tools.joint_investment(partners, total_profit, months))


@mcp.tool()
def tool_rent_vs_buy(price: float, monthly_rent: float, down_payment_pct: float = 0.20,
                     annual_rate: Optional[float] = None, years: Optional[int] = None,
                     cagr: float = 0.08, rent_growth: float = 0.05, hold_years: int = 10) -> str:
    """Compare buying against renting over a holding period."""
    return dump(tools.rent_vs_buy(price, monthly_rent, down_payment_pct, annual_rate, years,
                                  cagr, rent_growth, hold_years))


@mcp.tool()
def tool_construction_cost(covered_area: float, floors: int = 1, building_type: str = "house",
                           quality_tier: str = "standard", system: str = "rcc_frame",
                           city: Optional[str] = None, plot_area: Optional[float] = None,
                           escalation_years: float = 0.0) -> str:
    """Construction-cost estimate (delegates to the construction wing's engine)."""
    return dump(tools.construction_cost(covered_area, floors, building_type, quality_tier, system,
                                        city, plot_area, escalation_years))


@mcp.tool()
def tool_material_quantities(covered_area: float, quality_tier: str = "standard",
                             building_type: str = "house") -> str:
    """Approximate material take-off (delegates to the construction wing)."""
    return dump(tools.material_quantities(covered_area, quality_tier, building_type))


@mcp.tool()
def tool_build_timeline(covered_area: float, floors: int = 1, building_type: str = "house",
                        system: str = "rcc_frame") -> str:
    """Phase-weighted construction timeline (delegates to the construction wing)."""
    return dump(tools.build_timeline(covered_area, floors, building_type, system))


@mcp.tool()
def tool_calculators() -> str:
    """The calculators offered by the Tools Center, with their inputs and engines."""
    return dump(tools.calculator_catalog())


# ---------- GIS · georeferencing · map tools ----------


@mcp.tool()
def tool_crs_catalog() -> str:
    """Common coordinate reference systems with guidance on which to measure in."""
    return dump(tools.crs_catalog())


@mcp.tool()
def tool_map_measure(coords: List[List[float]], marla_sqft: float = 272.25) -> str:
    """Distance, perimeter, area, centroid and bbox for a set of [lat, lon] points."""
    return dump(tools.map_measure(coords, marla_sqft))


@mcp.tool()
def tool_polygon_area(coords: List[List[float]], unit: str = "sqft",
                      marla_sqft: float = 272.25) -> str:
    """Area of a polygon from its [lat, lon] coordinates, in the requested unit."""
    return dump(tools.polygon_area_tool(coords, unit, marla_sqft))


@mcp.tool()
def tool_georeference(control_points: List[Dict[str, Any]]) -> str:
    """Fit an image-pixel → WGS84 transform from control points (affine/similarity)."""
    return dump(tools.georeference(control_points))


@mcp.tool()
def tool_transform_point(matrix: Dict[str, float], x: float, y: float, to_geo: bool = True) -> str:
    """Apply a georeference matrix (px→geo forward, or geo→px with to_geo=False)."""
    return dump(tools.transform_point(matrix, x, y, to_geo))


@mcp.tool()
def tool_aerial_compare(scenes: List[Dict[str, Any]]) -> str:
    """Compare dated aerial/satellite scenes: order, resolution and change."""
    return dump(tools.aerial_compare(scenes))


@mcp.tool()
def tool_export_geodata(features: List[Dict[str, Any]], fmt: str = "geojson",
                        name: str = "export") -> str:
    """Export points/lines/polygons as GeoJSON or KML."""
    return dump(tools.export_geodata(features, fmt, name))


@mcp.tool()
def tool_import_geodata(text: str) -> str:
    """Parse GeoJSON or KML text into [lat, lon] coordinate lists."""
    return dump(tools.import_geodata(text))


@mcp.tool()
def tool_locate_nearby(origin: List[float], radius_m: float = 2000.0,
                       category: Optional[str] = None, limit: int = 20) -> str:
    """Locate POIs within a radius of an origin [lat, lon], nearest first."""
    return dump(tools.locate_nearby(origin, [model_dict(p) for p in pois_db], radius_m, category, limit))


@mcp.tool()
def tool_plot_studio(value: float, from_unit: str = "marla", ratio: float = 2.0,
                     covered_area: Optional[float] = None, quality_tier: str = "standard",
                     building_type: str = "house", marla_sqft: float = 272.25) -> str:
    """One-shot plot brief: all-unit conversion, dimensions, diagram and optional build cost."""
    return dump(tools.plot_studio(value, from_unit, ratio, covered_area, quality_tier,
                                  building_type, marla_sqft))


@mcp.tool()
def tool_plot_diagram(length_ft: float, width_ft: float, label: str = "Plot",
                      marla_sqft: float = 272.25) -> str:
    """A printable SVG diagram of a rectangular plot with its dimensions and area."""
    return dump(tools.plot_diagram_svg(length_ft, width_ft, label, marla_sqft))


# ---------- CAD · plan utilities ----------


@mcp.tool()
def tool_cad_formats() -> str:
    """Supported drawing formats and what each can actually preview/convert."""
    return dump(tools.cad_formats())


@mcp.tool()
def tool_cad_inspect(filename: str = "", head_base64: Optional[str] = None,
                     size_bytes: int = 0) -> str:
    """Detect a drawing's format from its name/first bytes and report capabilities."""
    return dump(tools.cad_inspect(filename, head_base64, size_bytes))


@mcp.tool()
def tool_dxf_preview(text: str, width: int = 800, height: int = 600) -> str:
    """Parse an ASCII DXF and render it to SVG (line/polyline/circle/text)."""
    return dump(tools.dxf_preview(text, width, height))


@mcp.tool()
def tool_compare_revisions(a_entities: List[Dict[str, Any]], b_entities: List[Dict[str, Any]]) -> str:
    """Compare two revisions of a plan: counts, extents and added/removed items."""
    return dump(tools.compare_revisions(a_entities, b_entities))


@mcp.tool()
def tool_printable_layout(title: str, plot_length_ft: float, plot_width_ft: float,
                          orientation: str = "portrait") -> str:
    """A printable plot-layout sheet (SVG) with a title block and scale bar."""
    return dump(tools.printable_layout_sheet(title, plot_length_ft, plot_width_ft, orientation))


# ---------- Photo location & geotagging ----------


@mcp.tool()
def tool_read_photo_gps(image_base64: str) -> str:
    """Read GPS coordinates, altitude and time from a JPEG's EXIF metadata."""
    return dump(tools.read_photo_gps(image_base64))


@mcp.tool()
def tool_write_photo_gps(image_base64: str, latitude: float, longitude: float,
                         altitude: Optional[float] = None, timestamp: Optional[str] = None) -> str:
    """Embed/replace GPS coordinates in a JPEG's EXIF (returns new base64 bytes)."""
    return dump(tools.write_photo_gps(image_base64, latitude, longitude, altitude, timestamp))


@mcp.tool()
def tool_photo_geotag_batch(photos: List[Dict[str, Any]], latitude: float, longitude: float,
                            altitude: Optional[float] = None) -> str:
    """Geotag several photos with the same coordinate."""
    return dump(tools.photo_geotag_batch(photos, latitude, longitude, altitude))


@mcp.tool()
def tool_photo_report(photos: List[Dict[str, Any]], title: str = "Site photo report",
                      lang: str = "en", theme: str = "auto") -> str:
    """A property photo report: markers, summary table and an embeddable map."""
    return dump(tools.photo_report(photos, title, lang, theme))


@mcp.tool()
def tool_geo_privacy_check(latitude: float, longitude: float) -> str:
    """Advise on sharing precise residential coordinates (opt-in, fuzzing)."""
    return dump(tools.geo_privacy_check(latitude, longitude))


# ---------- Document & file conversion ----------


@mcp.tool()
def tool_text_to_pdf(title: str, lines: List[str], page_size: str = "a4") -> str:
    """Create a simple text/listings PDF (dependency-free)."""
    return dump(tools.text_to_pdf(title, lines, page_size))


@mcp.tool()
def tool_images_to_pdf(images: List[Dict[str, Any]], page_size: str = "a4") -> str:
    """Combine JPEG images into a PDF (native, no re-encoding)."""
    return dump(tools.images_to_pdf(images, page_size))


@mcp.tool()
def tool_brochure_pdf(title: str, subtitle: str = "",
                      sections: Optional[List[Dict[str, Any]]] = None) -> str:
    """Build a branded text brochure PDF from a list of sections."""
    return dump(tools.brochure_pdf(title, subtitle, sections))


@mcp.tool()
def tool_pdf_info(pdf_base64: str) -> str:
    """Basic PDF inspection: page count and declared size."""
    return dump(tools.pdf_info(pdf_base64))


@mcp.tool()
def tool_image_resize_plan(width: int, height: int, max_width: int = 1600,
                           max_height: int = 1600) -> str:
    """Compute a contain-fit resize target without touching the pixels."""
    return dump(tools.image_resize_plan(width, height, max_width, max_height))


@mcp.tool()
def tool_convert_guide(kind: str) -> str:
    """Explain what a heavier conversion needs (and why), plus upload-safety notes."""
    return dump(tools.convert_guide(kind))


@mcp.tool()
def tool_document_tools() -> str:
    """The document/conversion tools and whether each is native or needs a dependency."""
    return dump(tools.document_tools())


# ---------- Pakistan & Islamic calendar ----------


@mcp.tool()
def tool_hijri_from_gregorian(on: str) -> str:
    """Convert a Gregorian date (YYYY-MM-DD) to the predicted Hijri date."""
    return dump(tools.hijri_from_gregorian(on))


@mcp.tool()
def tool_gregorian_from_hijri(year: int, month: int, day: int) -> str:
    """Convert a Hijri date to the predicted Gregorian date."""
    return dump(tools.gregorian_from_hijri(year, month, day))


@mcp.tool()
def tool_islamic_occasions(year: int) -> str:
    """The main Islamic occasions inside a Gregorian year (predicted)."""
    return dump(tools.islamic_occasions(year))


@mcp.tool()
def tool_pakistan_holidays(year: int) -> str:
    """Pakistan public holidays for a year: fixed national days + predicted Islamic ones."""
    return dump(tools.pakistan_holidays(year))


@mcp.tool()
def tool_calendar_ics(events: List[Dict[str, Any]], calendar_name: str = "Arz-e-Pak") -> str:
    """Render events as a downloadable iCalendar (.ics) feed."""
    return dump(tools.calendar_ics(events, calendar_name))


@mcp.tool()
def tool_property_reminders(events: List[Dict[str, Any]], lead_days: int = 7) -> str:
    """Turn dated property events into reminders (possession, installments, expiries)."""
    return dump(tools.property_reminders(events, lead_days))


@mcp.tool()
def tool_milestone_calendar(start_date: str, covered_area: float = 1000.0, floors: int = 1,
                            building_type: str = "house", system: str = "rcc_frame") -> str:
    """Date-stamp a construction timeline into a milestone calendar (+ .ics)."""
    return dump(tools.milestone_calendar(start_date, covered_area, floors, building_type, system))


@mcp.tool()
def tool_possession_schedule(start_date: str, total_price: float, down_payment: float = 0.0,
                             months: int = 24, frequency: str = "monthly") -> str:
    """A booking + installment + possession payment schedule with due dates (+ .ics)."""
    return dump(tools.possession_schedule(start_date, total_price, down_payment, months, frequency))


# ---------- Reports & export studio ----------


@mcp.tool()
def tool_property_comparison(properties: List[Dict[str, Any]]) -> str:
    """Side-by-side comparison of listings with derived price/sqft and yield."""
    return dump(tools.property_comparison(properties))


@mcp.tool()
def tool_investment_summary(initial_investment: float, annual_cash_flow: float = 0.0,
                            hold_years: int = 10, terminal_value: float = 0.0,
                            loan_amount: float = 0.0, loan_rate: Optional[float] = None) -> str:
    """Investment summary built on the accounting ROI engine (with scenarios)."""
    return dump(tools.investment_summary(initial_investment, annual_cash_flow, hold_years,
                                         terminal_value, loan_amount, loan_rate))


@mcp.tool()
def tool_plot_inventory(properties: List[Dict[str, Any]], marla_sqft: float = 272.25) -> str:
    """Plot inventory: area in sqft / marla / kanal with price per unit."""
    return dump(tools.plot_inventory(properties, marla_sqft))


@mcp.tool()
def tool_rows_to_csv(rows: List[Dict[str, Any]], columns: Optional[List[str]] = None) -> str:
    """Serialise rows of dicts to CSV text."""
    return dump(tools.rows_to_csv(rows, columns))


@mcp.tool()
def tool_rows_to_markdown(rows: List[Dict[str, Any]], columns: Optional[List[str]] = None) -> str:
    """Serialise rows of dicts to a Markdown table."""
    return dump(tools.rows_to_markdown(rows, columns))


# ---------- Tools Center: catalog, saved projects, portal page ----------


@mcp.tool()
def tools_overview() -> str:
    """Counts by category and phase, the native/optional split and the wing configuration."""
    return dump(tools.tools_overview())


@mcp.tool()
def tools_categories() -> str:
    """The Tools Center categories and how many tools each holds."""
    return dump(tools.tool_categories())


@mcp.tool()
def tools_catalog(category: Optional[str] = None, phase: Optional[int] = None) -> str:
    """The tool cards, optionally filtered by category or launch phase."""
    rows = tools.tools_by_category(category, phase)
    return dump({"count": len(rows), "category": category, "phase": phase, "tools": rows})


@mcp.tool()
def tool_get(key: str) -> str:
    """One tool card by key (e.g. ``mortgage``, ``georeference``, ``calendar``)."""
    return dump(tools.tool_view(key))


@mcp.tool()
def tool_save_project(name: str, tool: str, inputs: Optional[Dict[str, Any]] = None,
                      outputs: Optional[Dict[str, Any]] = None, notes: Optional[str] = None) -> str:
    """Save a tool run as a reusable project (personalised tools)."""
    rec = tools.save_project(name, tool, inputs, outputs, notes)
    return dump(model_dict(rec))


@mcp.tool()
def tool_projects(tool: Optional[str] = None) -> str:
    """List saved tool projects, optionally filtered by tool key."""
    rows = [model_dict(p) for p in tools.list_projects(tool)]
    return dump({"count": len(rows), "projects": rows})


@mcp.tool()
def tool_project_get(project_id: str) -> str:
    """One saved tool project by id."""
    rec = tools.find_project(project_id)
    if not rec:
        return dump({"error": f"Unknown project: {project_id}"})
    return dump(model_dict(rec))


@mcp.tool()
def tool_project_delete(project_id: str) -> str:
    """Delete a saved tool project."""
    return dump({"deleted": tools.delete_project(project_id), "project_id": project_id})


@mcp.tool()
def tools_portal(lang: str = "en", theme: str = "auto") -> str:
    """Render the **Tools & Utilities** page (HTML): a searchable Tools Center, live
    calculators, unit/CRS/CAD reference tables and the Pakistan & Islamic calendar —
    bilingual and themed."""
    ov = tools.tools_overview()
    c = ov["counts"]
    calc_rows = [[x["name"], ", ".join(x["inputs"]), x["engine"]]
                 for x in tools.calculator_catalog()["calculators"]]
    unit_rows = [[u, f"{tools._sqft_per(u):,.4f}", f"{tools._sqft_per(u, 225.0):,.4f}"]
                 for u in tools.AREA_UNITS]
    crs_rows = [[f"EPSG:{s['epsg']}", s["name"], s["units"], s["use"]] for s in tools.crs_catalog()["systems"]]
    cad_rows = [[f["format"], ", ".join(f["ext"]), f["preview"], f["convert"], f["layers"]]
                for f in tools.CAD_FORMATS]
    year = datetime.now().year
    hol = tools.pakistan_holidays(year)
    hol_rows = [[h["date"], h["name"], h["type"], "predicted" if h.get("predicted") else "fixed"]
                for h in hol["holidays"]]
    occ = tools.islamic_occasions(year)
    occ_rows = [[o["date"], o["name"], o["hijri"]] for o in occ["occasions"]]
    sections: List[Dict[str, Any]] = [
        {"kind": "cards", "heading": "Tools Center at a glance", "items": [
            ["Tools", c["tools"], f"{c['categories']} categories"],
            ["Calculators", c["calculators"], "finance & property"],
            ["Phases", len(ov["by_phase"]), "quick win → professional"],
            ["CRS systems", c["crs_systems"], "for accurate area"],
            ["Saved projects", c["saved_projects"], "personalised tools"]]},
        {"kind": "text", "heading": "About this wing", "text": (
            "The Tools & Utilities center is the portal's professional toolkit: property "
            "calculators, a plot & construction studio, GIS measurement and georeferencing, "
            "CAD/plan utilities, photo geotagging, document conversion, the Pakistan & Islamic "
            "calendar and a reports/export studio. Everything runs on one shared engine — the "
            "same MCP tools and REST endpoints return identical results. Where a capability "
            "genuinely needs a heavy or licensed dependency, the tool says so rather than "
            "faking the work.")},
        {"kind": "html", "heading": "Browse tools", "html": _tools_center_html()},
        {"kind": "html", "heading": "Live calculators", "html": _tools_calculator_html()},
        {"kind": "table", "heading": "Calculators",
         "columns": ["Tool", "Inputs", "Engine"], "rows": calc_rows},
        {"kind": "table", "heading": "Area units (sqft per unit; standard & small marla)",
         "columns": ["Unit", "Standard marla", "Small marla (225)"], "rows": unit_rows},
        {"kind": "table", "heading": "Coordinate reference systems",
         "columns": ["CRS", "Name", "Units", "Use"], "rows": crs_rows},
        {"kind": "table", "heading": "CAD & drawing formats",
         "columns": ["Format", "Extensions", "Preview", "Convert", "Layers"], "rows": cad_rows},
        {"kind": "table", "heading": f"Islamic occasions {year} (predicted)",
         "columns": ["Date", "Occasion", "Hijri"], "rows": occ_rows},
        {"kind": "table", "heading": f"Pakistan holidays {year}",
         "columns": ["Date", "Holiday", "Type", "Status"], "rows": hol_rows},
    ]
    ads = content.ad_section(slot="sidebar", category="services", lang=lang)
    if ads.get("count"):
        sections.append(ads)
    return gis.build_report_html(title="Tools & Utilities",
                                 subtitle="Calculate · map · convert · manage property",
                                 sections=sections, ticker_html=_portal_ticker(lang),
                                 lang=lang, theme=theme)


@mcp.resource("tools://overview", name="Tools overview",
              description="Counts, categories and configuration for the Tools Center.")
def res_tools_overview() -> str:
    return tools_overview()


@mcp.resource("tools://categories", name="Tool categories",
              description="The Tools Center categories and their tool counts.")
def res_tools_categories() -> str:
    return tools_categories()


@mcp.resource("tools://catalog", name="Tool catalog",
              description="Every tool card in the Tools Center.")
def res_tools_catalog() -> str:
    return tools_catalog()


@mcp.resource("tools://tool/{key}", name="Tool", description="One tool card by key.")
def res_tools_tool(key: str) -> str:
    return tool_get(key)


@mcp.resource("tools://units", name="Area & length units",
              description="Area units, marla standards and length units.")
def res_tools_units() -> str:
    return dump({"area": tools.area_units(), "length_feet_per_unit": tools.FEET_PER_UNIT})


@mcp.resource("tools://crs", name="Coordinate reference systems",
              description="Common CRS with measurement guidance.")
def res_tools_crs() -> str:
    return tool_crs_catalog()


@mcp.resource("tools://calculators", name="Calculators",
              description="The calculators offered by the Tools Center.")
def res_tools_calculators() -> str:
    return tool_calculators()


@mcp.resource("tools://calendar/{year}", name="Islamic occasions",
              description="Predicted Islamic occasions inside a Gregorian year.")
def res_tools_calendar(year: str) -> str:
    return tool_islamic_occasions(int(year))


@mcp.resource("tools://holidays/{year}", name="Pakistan holidays",
              description="Pakistan public holidays for a year.")
def res_tools_holidays(year: str) -> str:
    return tool_pakistan_holidays(int(year))


@mcp.prompt(name="tools_calculator_prompt",
            description="Pick and run the right property calculator for a question.")
def prompt_tools_calculator(question: str = "What is the monthly payment on a 1 crore loan?",
                            city: str = "Lahore") -> str:
    return (
        "You are a property-finance assistant for Pakistan.\n"
        f"Question: '{question}' in {city}.\n"
        "1. Choose the calculator with tool_calculators (mortgage, rental yield, transfer "
        "costs, capital gains, commission, joint investment, appreciation).\n"
        "2. Call the matching tool_* function; use tool_area_convert for units and "
        "tool_transfer_costs/tool_capital_gains_tax for statutory costs.\n"
        "3. Present the result with the assumptions, and flag that statutory rates are "
        "indicative and must be confirmed with the district office."
    )


@mcp.prompt(name="tools_gis_prompt",
            description="Measure a plot/plan and export it for a survey workflow.")
def prompt_tools_gis(plan: str = "scanned housing-scheme plan", target: str = "a 10 marla plot") -> str:
    return (
        "You are a GIS/survey assistant.\n"
        f"Task: align and measure {target} from {plan}.\n"
        "1. tool_georeference with control points to fit a pixel→WGS84 transform.\n"
        "2. tool_map_measure / tool_polygon_area for distance, perimeter and area in "
        "sqft/marla/kanal; tool_crs_catalog to pick the right CRS for area.\n"
        "3. tool_export_geodata to GeoJSON or KML, and tool_plot_studio for a printable diagram.\n"
        "4. State the RMSE/quality and the licensing/ownership caveats about imagery."
    )


# ============================================================
# ============ PMO WING (project management · monitoring · tracking) ======
# ============================================================
#
# The in-house running project-management, monitoring and tracking system.
# ``pmo.py`` is framework-free; these thin MCP tools and the ``/pmo/...`` REST
# routes in ``api.py`` share the very same functions.


def _pmo_bar_svg(rows: List[Dict[str, Any]]) -> str:
    """A compact horizontal progress-bar chart for the projects."""
    if not rows:
        return '<p style="color:var(--muted)">No projects yet.</p>'
    bar_w = 260
    out = ["<div style='display:flex;flex-direction:column;gap:8px'>"]
    for r in rows:
        pct = float(r.get("progress_pct") or 0.0)
        health = r.get("health", "green")
        color = pmo.RAG_COLORS.get(health, "#1b9e4b")
        filled = bar_w * max(0.0, min(100.0, pct)) / 100.0
        out.append(
            "<div style='display:flex;align-items:center;gap:10px;font-size:13px'>"
            f"<div style='width:230px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap'>{r.get('name','')}</div>"
            f"<svg width='{bar_w}' height='14'><rect width='{bar_w}' height='14' rx='3' fill='#e5e7eb'/>"
            f"<rect width='{filled:.1f}' height='14' rx='3' fill='{color}'/></svg>"
            f"<span style='width:44px;text-align:right'>{pct:.0f}%</span>"
            f"<span style='width:120px;color:var(--muted)'>{health.upper()} · {r.get('status','')}</span>"
            "</div>")
    out.append("</div>")
    return "".join(out)


def pmo_portal(lang: str = "en", theme: str = "auto") -> str:
    """The Project Management & Monitoring (PMO) page as HTML."""
    ov = pmo.pmo_overview()
    dash = pmo.portfolio_dashboard()
    alerts = pmo.alerts()
    proj_rows = [[r["code"], r["name"], r["status"], r["project_type"], r["city"] or "",
                  f"{r['progress_pct']:.0f}%", r["health"].upper(),
                  pmo.format_pkr(r["budget"]), pmo.format_pkr(r["actual_cost"]),
                  str(r["SPI"]), str(r["CPI"])] for r in dash["rows"]]
    cap_rows = [[c["name"], c["category"], c["blurb"]] for c in pmo.PM_CAPABILITIES]
    alert_rows = [[a["level"].upper(), a["project"], a["kind"], a["message"]] for a in alerts["alerts"][:20]]

    sections = [
        {"kind": "cards", "heading": "Portfolio", "items": [
            ("Projects", str(dash["projects"]), "in the register"),
            ("Revised budget", pmo.format_pkr(dash["financials"]["total_budget"]), "all projects"),
            ("Actual cost", pmo.format_pkr(dash["financials"]["total_actual"]), "spent"),
            ("Portfolio SPI", str(dash["portfolio_spi"]), "schedule index"),
            ("Portfolio CPI", str(dash["portfolio_cpi"]), "cost index"),
            ("Open alerts", str(alerts["count"]), f"{alerts['red']} red · {alerts['amber']} amber"),
        ]},
        {"kind": "html", "heading": "Progress", "html": _pmo_bar_svg(dash["rows"])},
        {"kind": "table", "heading": "Project register",
         "columns": ["Code", "Project", "Status", "Type", "City", "Progress", "Health",
                     "Budget", "Actual", "SPI", "CPI"],
         "rows": proj_rows},
        {"kind": "table", "heading": "What the PMO does",
         "columns": ["Capability", "Group", "What it does"], "rows": cap_rows},
        {"kind": "table", "heading": "Open alerts & exceptions",
         "columns": ["Level", "Project", "Kind", "Message"], "rows": alert_rows},
        {"kind": "text", "heading": "Method",
         "text": "Scheduling runs a forward/backward pass over the task network on a six-day "
                 "(Mon–Sat) working week to give float and the critical path; progress is "
                 "duration-weighted and earned value follows the standard PV/EV/AC definitions. "
                 + ov["disclaimer"]},
    ]
    ads = content.ad_section(slot="sidebar", category="services", lang=lang)
    if ads.get("count"):
        sections.append(ads)
    return gis.build_report_html(title="Projects & Monitoring (PMO)",
                                 subtitle="Plan · schedule · track · control",
                                 sections=sections, ticker_html=_portal_ticker(lang),
                                 lang=lang, theme=theme)


@mcp.tool()
def pmo_overview() -> str:
    """Counts, breakdowns and configuration for the whole PMO (project management) wing."""
    return dump(pmo.pmo_overview())


@mcp.tool()
def pmo_capabilities() -> str:
    """The PMO capabilities grouped by category (planning, tracking, monitoring, governance)."""
    return dump(pmo.capabilities())


@mcp.tool()
def pm_project_types() -> str:
    """The supported project types, statuses and priorities."""
    return dump(pmo.project_types())


@mcp.tool()
def pm_phase_templates(project_type: Optional[str] = None) -> str:
    """Default weighted phase templates by project type (or all templates)."""
    return dump(pmo.phase_templates(project_type))


@mcp.tool()
def pm_create_project(
    name: str, project_type: str = "construction", description: Optional[str] = None,
    city: Optional[str] = None, scheme: Optional[str] = None, client: Optional[str] = None,
    manager_id: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None,
    budget: float = 0.0, contract_value: float = 0.0, priority: str = "medium",
    status: str = "planning", tags: Optional[List[str]] = None, with_template: bool = True,
) -> str:
    """Register a project (optionally seeding its weighted phases and WBS template)."""
    return dump(pmo.create_project(
        name, project_type=project_type, description=description, city=city, scheme=scheme,
        client=client, manager_id=manager_id, start_date=start_date, end_date=end_date,
        budget=budget, contract_value=contract_value, priority=priority, status=status,
        tags=tags, with_template=with_template))


@mcp.tool()
def pm_projects(status: Optional[str] = None, project_type: Optional[str] = None,
                 city: Optional[str] = None, manager_id: Optional[str] = None,
                 priority: Optional[str] = None, limit: int = 50) -> str:
    """List projects with progress and health (filter by status, type, city, manager, priority)."""
    return dump(pmo.list_projects(status=status, project_type=project_type, city=city,
                                  manager_id=manager_id, priority=priority, limit=limit))


@mcp.tool()
def pm_project(project_id: str) -> str:
    """One project by id or code, with phase/task/milestone counts."""
    return dump(pmo.get_project(project_id))


@mcp.tool()
def pm_update_project(project_id: str, updates: Dict[str, Any]) -> str:
    """Update a project's fields (name, status, priority, budget, dates, client, tags …)."""
    return dump(pmo.update_project(project_id, **(updates or {})))


@mcp.tool()
def pm_delete_project(project_id: str) -> str:
    """Delete a project and everything that belongs to it (tasks, costs, risks, logs …)."""
    return dump(pmo.delete_project(project_id))


@mcp.tool()
def pm_project_dashboard(project_id: str) -> str:
    """The full project-controls snapshot: health, KPI, progress, cost, EVM, alerts and risks."""
    return dump(pmo.monitoring_snapshot(project_id))


@mcp.tool()
def pm_from_estimate(estimate_id: str, name: Optional[str] = None, city: Optional[str] = None,
                      start_date: Optional[str] = None, contract_value: Optional[float] = None) -> str:
    """Create a delivery project from a saved Construction-wing estimate (budget = build cost)."""
    return dump(pmo.import_construction_estimate(
        estimate_id, name=name, city=city, start_date=start_date, contract_value=contract_value))


@mcp.tool()
def pm_apply_template(project_id: str, project_type: Optional[str] = None) -> str:
    """Seed a project's weighted phases and a task work-breakdown from its type template."""
    return dump(pmo.apply_template(project_id, project_type))


@mcp.tool()
def pm_add_phase(project_id: str, name: str, key: Optional[str] = None, weight: float = 0.0,
                  order: Optional[int] = None, planned_start: Optional[str] = None,
                  planned_end: Optional[str] = None) -> str:
    """Add a weighted phase to a project's work-breakdown."""
    return dump(pmo.add_phase(project_id, name, key=key, weight=weight, order=order,
                              planned_start=planned_start, planned_end=planned_end))


@mcp.tool()
def pm_phases(project_id: str) -> str:
    """List a project's phases with normalised weights and progress."""
    return dump(pmo.list_phases(project_id))


@mcp.tool()
def pm_add_milestone(project_id: str, name: str, planned_date: Optional[str] = None,
                      phase_key: Optional[str] = None, task_id: Optional[str] = None,
                      weight: float = 1.0, billable_amount: float = 0.0,
                      notes: Optional[str] = None) -> str:
    """Add a milestone (optionally linked to a task and a billable amount)."""
    return dump(pmo.add_milestone(project_id, name, planned_date=planned_date, phase_key=phase_key,
                                  task_id=task_id, weight=weight, billable_amount=billable_amount,
                                  notes=notes))


@mcp.tool()
def pm_milestones(project_id: str, status: Optional[str] = None) -> str:
    """List a project's milestones with forecast dates and slip."""
    return dump(pmo.list_milestones(project_id, status=status))


@mcp.tool()
def pm_add_task(project_id: str, name: str, phase_key: Optional[str] = None,
                 duration_days: int = 1, predecessors: Optional[List[str]] = None,
                 assignee_id: Optional[str] = None, weight: float = 0.0,
                 cost_budget: float = 0.0, priority: str = "medium",
                 wbs: Optional[str] = None, notes: Optional[str] = None) -> str:
    """Add a task (duration in working days, finish-to-start predecessors)."""
    return dump(pmo.add_task(project_id, name, phase_key=phase_key, duration_days=duration_days,
                             predecessors=predecessors, assignee_id=assignee_id, weight=weight,
                             cost_budget=cost_budget, priority=priority, wbs=wbs, notes=notes))


@mcp.tool()
def pm_tasks(project_id: str, phase_key: Optional[str] = None, status: Optional[str] = None,
              assignee_id: Optional[str] = None) -> str:
    """List tasks with their scheduled start/finish, float and critical flag."""
    return dump(pmo.list_tasks(project_id, phase_key=phase_key, status=status, assignee_id=assignee_id))


@mcp.tool()
def pm_task(task_id: str) -> str:
    """One task by id, with its scheduled start/finish, float and critical flag."""
    t = pmo.find_task(task_id)
    if not t:
        return dump({"error": f"Unknown task: {task_id}"})
    sched = {r["id"]: r for r in pmo.build_schedule(t.project_id).get("tasks", [])}
    row = pmo._m(t)
    row.update({k: sched.get(t.id, {}).get(k) for k in
                ("planned_start", "planned_finish", "late_start", "late_finish",
                 "float_days", "is_critical")})
    return dump(row)


@mcp.tool()
def pm_update_task(task_id: str, updates: Dict[str, Any]) -> str:
    """Update a task (progress %, status, dates, duration, assignee, cost …)."""
    return dump(pmo.update_task(task_id, **(updates or {})))


@mcp.tool()
def pm_delete_task(task_id: str) -> str:
    """Delete a task and its resource allocations."""
    return dump(pmo.delete_task(task_id))


@mcp.tool()
def pm_schedule(project_id: str, start_date: Optional[str] = None) -> str:
    """Run the forward/backward pass: ES/EF, LS/LF, total float and the critical path."""
    return dump(pmo.build_schedule(project_id, start_date=start_date))


@mcp.tool()
def pm_critical_path(project_id: str) -> str:
    """The critical path (zero-float chain) with its entries and the project duration."""
    return dump(pmo.critical_path(project_id))


@mcp.tool()
def pm_gantt(project_id: str) -> str:
    """Gantt-ready rows (phase, task, start, finish, progress, critical) for a project."""
    return dump(pmo.gantt(project_id))


@mcp.tool()
def pm_add_cost(project_id: str, amount: float, category: str = "other",
                 description: str = "", kind: str = "actual", date: Optional[str] = None,
                 vendor: Optional[str] = None, invoice_ref: Optional[str] = None,
                 recorded_by: Optional[str] = None) -> str:
    """Record a committed or actual cost entry against a project."""
    return dump(pmo.add_cost(project_id, amount, category=category, description=description,
                             kind=kind, date=date, vendor=vendor, invoice_ref=invoice_ref,
                             recorded_by=recorded_by))


@mcp.tool()
def pm_costs(project_id: str, kind: Optional[str] = None, category: Optional[str] = None) -> str:
    """List a project's cost entries (filter by kind/category)."""
    return dump(pmo.list_costs(project_id, kind=kind, category=category))


@mcp.tool()
def pm_record_progress(project_id: str, percent: float, note: Optional[str] = None,
                        by: Optional[str] = None, manpower: int = 0,
                        weather: Optional[str] = None, on: Optional[str] = None) -> str:
    """Record a dated progress update for a project."""
    return dump(pmo.record_progress(project_id, percent, note=note, by=by, manpower=manpower,
                                    weather=weather, on=on))


@mcp.tool()
def pm_progress(project_id: str) -> str:
    """Current actual vs planned (duration-weighted) completion for a project."""
    return dump({**pmo.project_progress(project_id), "history": pmo.progress_history(project_id)})


@mcp.tool()
def pm_earned_value(project_id: str, as_of: Optional[str] = None) -> str:
    """Earned-value analysis: PV, EV, AC, SV, CV, SPI, CPI, EAC, ETC, VAC and TCPI."""
    return dump(pmo.earned_value(project_id, as_of=as_of))


@mcp.tool()
def pm_cost_status(project_id: str) -> str:
    """Cost control: baseline, approved variations, revised budget, commitments, actuals and forecast."""
    return dump(pmo.cost_status(project_id))


@mcp.tool()
def pm_s_curve(project_id: str, weeks: int = 52) -> str:
    """The planned-vs-actual S-curve (weekly cumulative completion) for a project."""
    return dump(pmo.s_curve(project_id, weeks=weeks))


@mcp.tool()
def pm_add_resource(name: str, role: str = "engineer", trade: Optional[str] = None,
                     day_rate: float = 0.0, capacity_pct: float = 100.0,
                     skills: Optional[List[str]] = None, contact: Optional[str] = None) -> str:
    """Register a team/trade resource with a day rate and capacity."""
    return dump(pmo.add_resource(name, role=role, trade=trade, day_rate=day_rate,
                                 capacity_pct=capacity_pct, skills=skills, contact=contact))


@mcp.tool()
def pm_resources(trade: Optional[str] = None, active_only: bool = False) -> str:
    """List resources (filter by trade; optionally active only)."""
    return dump(pmo.list_resources(trade=trade, active_only=active_only))


@mcp.tool()
def pm_assign(task_id: str, resource_id: str, units_pct: float = 100.0,
               notes: Optional[str] = None) -> str:
    """Assign a resource to a task at a percentage of their capacity."""
    return dump(pmo.assign(task_id, resource_id, units_pct=units_pct, notes=notes))


@mcp.tool()
def pm_resource_load(project_id: Optional[str] = None, window_start: Optional[str] = None,
                      window_end: Optional[str] = None) -> str:
    """Planned resource utilisation over a window, with over-allocation flags."""
    return dump(pmo.resource_load(project_id=project_id, window_start=window_start,
                                  window_end=window_end))


@mcp.tool()
def pm_health(project_id: str) -> str:
    """Schedule/cost/risk/quality RAG status and an overall health verdict."""
    return dump(pmo.project_health(project_id))


@mcp.tool()
def pm_alerts(project_id: Optional[str] = None) -> str:
    """Exception-based alerts for one project or the whole portfolio."""
    return dump(pmo.alerts(project_id))


@mcp.tool()
def pm_kpi(project_id: str) -> str:
    """The KPI scorecard for a project."""
    return dump(pmo.kpi(project_id))


@mcp.tool()
def pm_monitoring(project_id: str) -> str:
    """Alias of the project-controls snapshot (health, KPI, progress, cost, EVM, alerts)."""
    return dump(pmo.monitoring_snapshot(project_id))


@mcp.tool()
def pm_portfolio() -> str:
    """Rolled-up dashboard across every running project with portfolio SPI/CPI."""
    return dump(pmo.portfolio_dashboard())


@mcp.tool()
def pm_add_risk(project_id: str, title: str, kind: str = "risk", probability: int = 3,
                 impact: int = 3, description: Optional[str] = None, category: Optional[str] = None,
                 owner: Optional[str] = None, mitigation: Optional[str] = None,
                 due_on: Optional[str] = None) -> str:
    """Add a RAID item (risk/issue/assumption/dependency) with probability and impact (1–5)."""
    return dump(pmo.add_risk(project_id, title, kind=kind, probability=probability, impact=impact,
                             description=description, category=category, owner=owner,
                             mitigation=mitigation, due_on=due_on))


@mcp.tool()
def pm_risks(project_id: Optional[str] = None, kind: Optional[str] = None,
              status: Optional[str] = None, min_score: int = 0) -> str:
    """List RAID items with their score and band (sorted by score)."""
    return dump(pmo.list_risks(project_id=project_id, kind=kind, status=status, min_score=min_score))


@mcp.tool()
def pm_update_risk(risk_id: str, updates: Dict[str, Any]) -> str:
    """Update a RAID item (probability, impact, status, owner, mitigation …)."""
    return dump(pmo.update_risk(risk_id, **(updates or {})))


@mcp.tool()
def pm_risk_matrix(project_id: Optional[str] = None) -> str:
    """The probability × impact risk matrix with the placed RAID items."""
    return dump(pmo.risk_matrix(project_id))


@mcp.tool()
def pm_log_site(project_id: str, date: Optional[str] = None, weather: Optional[str] = None,
                 manpower: int = 0, equipment: Optional[List[str]] = None,
                 work_done: Optional[str] = None, issues: Optional[str] = None,
                 safety_incidents: int = 0, visitors: Optional[str] = None,
                 photos: Optional[List[str]] = None, by: Optional[str] = None) -> str:
    """Record a daily site diary entry (weather, manpower, plant, work, safety)."""
    return dump(pmo.log_site_day(project_id, date=date, weather=weather, manpower=manpower,
                                 equipment=equipment, work_done=work_done, issues=issues,
                                 safety_incidents=safety_incidents, visitors=visitors,
                                 photos=photos, by=by))


@mcp.tool()
def pm_site_logs(project_id: str, limit: int = 30) -> str:
    """List a project's site diary entries."""
    return dump(pmo.list_site_logs(project_id, limit=limit))


@mcp.tool()
def pm_site_report(project_id: str, on: Optional[str] = None) -> str:
    """A daily site report: the diary entry, progress, health and open alerts."""
    return dump(pmo.site_report(project_id, on=on))


@mcp.tool()
def pm_raise_change(project_id: str, title: str, description: Optional[str] = None,
                     reason: Optional[str] = None, cost_impact: float = 0.0,
                     schedule_impact_days: int = 0, requested_by: Optional[str] = None,
                     status: str = "submitted") -> str:
    """Raise a variation / change request with cost and schedule impact."""
    return dump(pmo.raise_change(project_id, title, description=description, reason=reason,
                                 cost_impact=cost_impact, schedule_impact_days=schedule_impact_days,
                                 requested_by=requested_by, status=status))


@mcp.tool()
def pm_changes(project_id: str, status: Optional[str] = None) -> str:
    """List a project's change requests with the approved cost/schedule impact."""
    return dump(pmo.list_changes(project_id, status=status))


@mcp.tool()
def pm_decide_change(change_id: str, approve: bool = True, by: Optional[str] = None,
                      note: Optional[str] = None) -> str:
    """Approve or reject a change request (approval moves the project's revised budget)."""
    return dump(pmo.decide_change(change_id, approve=approve, by=by, note=note))


@mcp.tool()
def pm_add_inspection(project_id: str, title: str,
                       checklist: Optional[List[Dict[str, Any]]] = None,
                       phase_key: Optional[str] = None, area: Optional[str] = None,
                       inspector: Optional[str] = None, date: Optional[str] = None,
                       status: str = "open", notes: Optional[str] = None) -> str:
    """Record a stage inspection with a pass/fail checklist; updates the quality index."""
    return dump(pmo.add_inspection(project_id, title, checklist=checklist, phase_key=phase_key,
                                   area=area, inspector=inspector, date=date, status=status,
                                   notes=notes))


@mcp.tool()
def pm_inspections(project_id: str, status: Optional[str] = None) -> str:
    """List a project's inspections and the aggregated quality index."""
    return dump(pmo.list_inspections(project_id, status=status))


@mcp.tool()
def pm_add_action(project_id: str, title: str, owner: Optional[str] = None,
                   due_on: Optional[str] = None, priority: str = "medium",
                   meeting: Optional[str] = None, notes: Optional[str] = None) -> str:
    """Add a meeting action item with an owner and due date."""
    return dump(pmo.add_action(project_id, title, owner=owner, due_on=due_on, priority=priority,
                               meeting=meeting, notes=notes))


@mcp.tool()
def pm_actions(project_id: Optional[str] = None, status: Optional[str] = None) -> str:
    """List action items (optionally for one project / one status)."""
    return dump(pmo.list_actions(project_id=project_id, status=status))


@mcp.tool()
def pm_close_action(action_id: str, status: str = "done") -> str:
    """Close (or reopen) a meeting action item."""
    return dump(pmo.close_action(action_id, status=status))


@mcp.tool()
def pm_project_report(project_id: str) -> str:
    """A full project status report as structured data (schedule, cost, EVM, risks, alerts)."""
    return dump(pmo.project_report(project_id))


@mcp.tool()
def pm_report_html(project_id: str, lang: str = "en", theme: str = "auto") -> str:
    """A printable project status report as (themed, bilingual) HTML."""
    return pmo.report_html(project_id, lang=lang, theme=theme)


@mcp.tool()
def pm_portal(lang: str = "en", theme: str = "auto") -> str:
    """The Projects & Monitoring (PMO) page as HTML: register, capabilities and alerts."""
    return pmo_portal(lang=lang, theme=theme)


@mcp.resource("pmo://overview", name="PMO overview",
              description="Counts, breakdowns and configuration for the PMO wing.")
def res_pmo_overview() -> str:
    return pmo_overview()


@mcp.resource("pmo://capabilities", name="PMO capabilities",
              description="The project-management capabilities by category.")
def res_pmo_capabilities() -> str:
    return pmo_capabilities()


@mcp.resource("pmo://project-types", name="Project types",
              description="Supported project types, statuses and priorities.")
def res_pmo_project_types() -> str:
    return pm_project_types()


@mcp.resource("pmo://phase-templates", name="Phase templates",
              description="Default weighted phase templates by project type.")
def res_pmo_phase_templates() -> str:
    return pm_phase_templates()


@mcp.resource("pmo://projects", name="Project register",
              description="Every project with progress and health.")
def res_pmo_projects() -> str:
    return pm_projects()


@mcp.resource("pmo://project/{project_id}", name="Project",
              description="One project with its counts and full status report.")
def res_pmo_project(project_id: str) -> str:
    return pm_project_report(project_id)


@mcp.resource("pmo://portfolio", name="Portfolio dashboard",
              description="The rolled-up portfolio dashboard.")
def res_pmo_portfolio() -> str:
    return pm_portfolio()


@mcp.resource("pmo://risk-matrix", name="Risk matrix",
              description="The portfolio-wide probability × impact risk matrix.")
def res_pmo_risk_matrix() -> str:
    return pm_risk_matrix()


@mcp.prompt(name="pm_project_kickoff_prompt",
            description="Kick off a new build/development project in the PMO.")
def prompt_pm_kickoff(name: str = "New apartment block", city: str = "Lahore",
                       budget: float = 250000000.0) -> str:
    return (
        "You are a project controls manager for a Pakistani developer.\n"
        f"Project to set up: '{name}' in {city}, budget approx {pmo.format_pkr(budget)}.\n"
        "1. pm_project_types + pm_phase_templates to choose the type and phases.\n"
        "2. pm_create_project (with_template=true) then pm_resources / pm_assign to staff it.\n"
        "3. pm_schedule to obtain the critical path, pm_milestones to set payment milestones.\n"
        "4. Report the plan: duration, critical path, phase weights and the milestone schedule."
    )


@mcp.prompt(name="pm_weekly_review_prompt",
            description="Run the weekly project-controls review for a project.")
def prompt_pm_weekly(project_id: str = "", focus: str = "schedule and cost") -> str:
    return (
        "You are running the weekly project-controls review"
        + (f" for project {project_id}" if project_id else "") + ".\n"
        f"Focus: {focus}.\n"
        "1. pm_monitoring (or pm_project_dashboard) for health, EVM and the S-curve.\n"
        "2. pm_alerts for exceptions; pm_tasks(status='blocked') and overdue milestones.\n"
        "3. pm_risk_matrix for top risks; pm_inspections for quality holds.\n"
        "4. Produce minutes: RAG status, variances (SV/CV, SPI/CPI), top 5 actions with owners."
    )


@mcp.prompt(name="pm_risk_review_prompt",
            description="Review and reprioritise the RAID register for a project.")
def prompt_pm_risk(project_id: str = "", horizon_days: int = 30) -> str:
    return (
        "You are the risk manager.\n"
        + (f"Project: {project_id}.\n" if project_id else "Scope: whole portfolio.\n")
        + f"Horizon: next {horizon_days} days.\n"
        "1. pm_risks and pm_risk_matrix to score the register (P×I).\n"
        "2. For every high/extreme item propose a mitigation, an owner and a due date "
        "(pm_update_risk).\n"
        "3. Convert accepted risks into schedule/cost contingency (pm_raise_change) and, where "
        "needed, into action items (pm_add_action)."
    )


# ============================================================
# ====== TEAM MESSAGING & NOTIFICATIONS ======================
# ============================================================
#
# Framework-free logic lives in ``messaging``; everything below is the MCP
# surface for it.  ``api.py`` reuses the very same functions over REST and adds a
# WebSocket feed on top of ``messaging.subscribe``.


@mcp.tool()
def msg_overview() -> str:
    """Team-messaging overview: config, channels, categories, counts and rollout plan."""
    return dump(messaging.messaging_overview())


@mcp.tool()
def msg_channels(channel_key: Optional[str] = None) -> str:
    """Default team channels (Sales, Property Verification, GIS & Mapping, Support, Management)."""
    return dump(messaging.messaging_channels(channel_key))


@mcp.tool()
def msg_categories(category: Optional[str] = None) -> str:
    """Notification categories with their default delivery channels and urgency."""
    return dump(messaging.notification_categories(category))


@mcp.tool()
def msg_attachment_kinds(kind: Optional[str] = None) -> str:
    """Attachment kinds, accepted extensions and default sensitivity."""
    return dump(messaging.attachment_rules(kind))


@mcp.tool()
def msg_profiles(presence: Optional[str] = None, role: Optional[str] = None,
                 query: Optional[str] = None) -> str:
    """Team directory of messaging profiles (filter by presence, role or text)."""
    return dump(messaging.list_profiles(presence=presence, role=role, query=query))


@mcp.tool()
def msg_set_presence(user_id: str, presence: str = "online") -> str:
    """Set a user's presence (online/away/busy/offline) and stamp last-seen."""
    return dump(messaging.set_presence(user_id, presence))


@mcp.tool()
def msg_presence_heartbeat(user_id: str, presence: Optional[str] = None) -> str:
    """Heartbeat a user's presence without spamming the audit trail."""
    return dump(messaging.touch_presence(user_id, presence))


@mcp.tool()
def msg_preferences(user_id: str) -> str:
    """A user's notification preferences, quiet hours, digest mode and Telegram state."""
    return dump(messaging.get_preferences(user_id))


@mcp.tool()
def msg_set_preferences(user_id: str, prefs: Optional[Dict[str, List[str]]] = None,
                        quiet_start: Optional[str] = None, quiet_end: Optional[str] = None,
                        digest: Optional[str] = None, telegram_opt_in: Optional[bool] = None,
                        telegram_categories: Optional[List[str]] = None) -> str:
    """Update per-category channels, quiet hours, digest mode and Telegram opt-in."""
    quiet = {"start": quiet_start, "end": quiet_end} if (quiet_start or quiet_end) else None
    return dump(messaging.set_preferences(user_id, prefs=prefs, quiet_hours=quiet, digest=digest,
                                          telegram_opt_in=telegram_opt_in,
                                          telegram_categories=telegram_categories))


@mcp.tool()
def msg_create_conversation(kind: str = "group", title: str = "", created_by: Optional[str] = None,
                            participants: Optional[List[str]] = None, channel_key: Optional[str] = None,
                            property_id: Optional[str] = None, topic: Optional[str] = None,
                            restricted: Optional[bool] = None, roles_allowed: Optional[List[str]] = None,
                            retention_days: Optional[int] = None,
                            announcement: Optional[str] = None) -> str:
    """Create a direct / group / channel / property conversation and seed its members."""
    return dump(messaging.create_conversation(
        kind=kind, title=title, created_by=created_by, participants=participants,
        channel_key=channel_key, property_id=property_id, topic=topic, restricted=restricted,
        roles_allowed=roles_allowed, retention_days=retention_days, announcement=announcement))


@mcp.tool()
def msg_conversations(user_id: str, kind: Optional[str] = None, include_archived: bool = False,
                      property_id: Optional[str] = None, channel_key: Optional[str] = None) -> str:
    """List a user's conversations with unread counts, newest activity first."""
    return dump(messaging.list_conversations(user_id, kind=kind, include_archived=include_archived,
                                             property_id=property_id, channel_key=channel_key))


@mcp.tool()
def msg_conversation(conversation_id: str, user_id: str) -> str:
    """One conversation with members, pins, unread count and full context."""
    return dump(messaging.get_conversation(conversation_id, user_id))


@mcp.tool()
def msg_conversation_context(conversation_id: str, user_id: Optional[str] = None) -> str:
    """What a conversation is tied to: property, pinned messages, actions, attachments."""
    return dump(messaging.conversation_context(conversation_id, user_id))


@mcp.tool()
def msg_archive_conversation(conversation_id: str, user_id: str, archived: bool = True) -> str:
    """Archive or restore a conversation (owner/admin only)."""
    return dump(messaging.archive_conversation(conversation_id, user_id, archived))


@mcp.tool()
def msg_members(conversation_id: str, user_id: Optional[str] = None) -> str:
    """Members of a conversation with roles, presence and read positions."""
    return dump(messaging.list_members(conversation_id, user_id))


@mcp.tool()
def msg_add_member(conversation_id: str, member_id: str, actor_id: Optional[str] = None,
                   role: str = "member") -> str:
    """Add (or re-role) a member of a conversation."""
    return dump(messaging.add_member(conversation_id, member_id, actor_id=actor_id, role=role))


@mcp.tool()
def msg_remove_member(conversation_id: str, member_id: str, actor_id: Optional[str] = None,
                      reason: Optional[str] = None) -> str:
    """Remove a member from a conversation (audited access revocation)."""
    return dump(messaging.remove_member(conversation_id, member_id, actor_id=actor_id, reason=reason))


@mcp.tool()
def msg_update_member(conversation_id: str, member_id: str, actor_id: Optional[str] = None,
                      role: Optional[str] = None, muted: Optional[bool] = None,
                      pinned: Optional[bool] = None, notification_level: Optional[str] = None) -> str:
    """Update a member's role, mute/pin state or notification level."""
    return dump(messaging.update_member(conversation_id, member_id, actor_id=actor_id, role=role,
                                        muted=muted, pinned=pinned,
                                        notification_level=notification_level))


@mcp.tool()
def msg_direct(user_a: str, user_b: str) -> str:
    """Find or create the 1-to-1 conversation between two users."""
    return dump(messaging.get_or_create_direct(user_a, user_b))


@mcp.tool()
def msg_property_thread(property_id: str, created_by: Optional[str] = None,
                        title: Optional[str] = None) -> str:
    """Get or create the internal discussion panel for a property record."""
    if find_property(property_id) is None:
        return dump({"error": f"property '{property_id}' not found"})
    return dump(messaging.get_or_create_property_thread(property_id, created_by=created_by, title=title))


@mcp.tool()
def msg_revoke_access(user_id: str, actor_id: Optional[str] = None, reason: Optional[str] = None) -> str:
    """Revoke a user's access to every conversation and unlink Telegram (staff leaving)."""
    return dump(messaging.revoke_user_access(user_id, actor_id=actor_id, reason=reason))


@mcp.tool()
def msg_post(conversation_id: str, author_id: str, body: str = "",
             message_type: str = "text", parent_id: Optional[str] = None,
             mentions: Optional[List[str]] = None, attachment_ids: Optional[List[str]] = None,
             property_id: Optional[str] = None) -> str:
    """Post a message (checked for membership, length and rate limit); notifies recipients."""
    return dump(messaging.post_message(conversation_id, author_id, body, message_type=message_type,
                                       parent_id=parent_id, mentions=mentions,
                                       attachment_ids=attachment_ids, property_id=property_id))


@mcp.tool()
def msg_messages(conversation_id: str, user_id: str, limit: int = 50,
                 before_seq: Optional[int] = None, thread_id: Optional[str] = None,
                 include_deleted: bool = False) -> str:
    """Page through a conversation's messages (or one thread), oldest to newest."""
    return dump(messaging.list_messages(conversation_id, user_id, limit=limit, before_seq=before_seq,
                                        thread_id=thread_id, include_deleted=include_deleted))


@mcp.tool()
def msg_message(message_id: str, user_id: str) -> str:
    """One message with its attachments, reactions, read receipts and replies."""
    return dump(messaging.get_message(message_id, user_id))


@mcp.tool()
def msg_edit_message(message_id: str, user_id: str, body: str) -> str:
    """Edit a message (author only, within the edit window)."""
    return dump(messaging.edit_message(message_id, user_id, body))


@mcp.tool()
def msg_delete_message(message_id: str, user_id: str, reason: Optional[str] = None) -> str:
    """Soft-delete a message (author or conversation admin)."""
    return dump(messaging.delete_message(message_id, user_id, reason))


@mcp.tool()
def msg_pin_message(message_id: str, user_id: str, pinned: bool = True) -> str:
    """Pin or unpin a message in its conversation."""
    return dump(messaging.pin_message(message_id, user_id, pinned))


@mcp.tool()
def msg_react(message_id: str, user_id: str, emoji: str) -> str:
    """Toggle an emoji reaction on a message."""
    return dump(messaging.react_to_message(message_id, user_id, emoji))


@mcp.tool()
def msg_thread(message_id: str, user_id: str, limit: int = 100) -> str:
    """The threaded replies to a message."""
    return dump(messaging.thread(message_id, user_id, limit))


@mcp.tool()
def msg_search(user_id: str, query: str = "", conversation_id: Optional[str] = None,
               property_id: Optional[str] = None, mention: Optional[str] = None,
               limit: int = 25) -> str:
    """Search messages across every conversation the user may access."""
    return dump(messaging.search_messages(user_id, query, conversation_id=conversation_id,
                                          property_id=property_id, mention=mention, limit=limit))


@mcp.tool()
def msg_mark_read(conversation_id: str, user_id: str, up_to_seq: Optional[int] = None) -> str:
    """Mark a conversation read up to a sequence number (defaults to the latest)."""
    return dump(messaging.mark_read(conversation_id, user_id, up_to_seq))


@mcp.tool()
def msg_unread(user_id: str) -> str:
    """Unread totals overall and per conversation, plus mention count."""
    return dump(messaging.unread_counts(user_id))


@mcp.tool()
def msg_read_receipts(message_id: str, user_id: str) -> str:
    """Who has read a message (read receipts)."""
    return dump(messaging.read_receipts(message_id, user_id))


@mcp.tool()
def msg_summarize(conversation_id: str, user_id: str, limit: int = 80) -> str:
    """Rules-based extractive summary: participants, topics, keywords and salient lines."""
    return dump(messaging.summarize_conversation(conversation_id, user_id, limit))


@mcp.tool()
def msg_action_items(conversation_id: str, user_id: str, limit: int = 100,
                     create: bool = False, owner_default: Optional[str] = None) -> str:
    """Extract action items from a conversation (optionally create tracked actions)."""
    return dump(messaging.extract_action_items(conversation_id, user_id, limit=limit, create=create,
                                               owner_default=owner_default))


@mcp.tool()
def msg_attach(conversation_id: str, uploaded_by: str, filename: str,
               kind: Optional[str] = None, size_bytes: int = 0, mime: Optional[str] = None,
               storage_key: Optional[str] = None, source_url: Optional[str] = None,
               sensitivity: Optional[str] = None, linked_type: Optional[str] = None,
               linked_id: Optional[str] = None) -> str:
    """Register a file reference (controlled storage or an existing portal record)."""
    return dump(messaging.register_attachment(
        conversation_id, uploaded_by, filename, kind=kind, size_bytes=size_bytes, mime=mime,
        storage_key=storage_key, source_url=source_url, sensitivity=sensitivity,
        linked_type=linked_type, linked_id=linked_id))


@mcp.tool()
def msg_attachment_link(attachment_id: str, user_id: str,
                        ttl_minutes: Optional[int] = None) -> str:
    """Mint a signed, expiring, permission-checked download link for an attachment."""
    return dump(messaging.attachment_link(attachment_id, user_id, ttl_minutes))


@mcp.tool()
def msg_attachment_resolve(token: str, user_id: Optional[str] = None) -> str:
    """Verify a signed attachment link (signature + expiry) and re-check access."""
    return dump(messaging.resolve_attachment_link(token, user_id))


@mcp.tool()
def msg_attachments(conversation_id: str, user_id: str, kind: Optional[str] = None,
                    sensitivity: Optional[str] = None) -> str:
    """List a conversation's shared files (references, never embedded content)."""
    return dump(messaging.list_attachments(conversation_id, user_id, kind=kind,
                                           sensitivity=sensitivity))


@mcp.tool()
def msg_create_action(conversation_id: str, created_by: str, title: str, kind: str = "task",
                      message_id: Optional[str] = None, detail: Optional[str] = None,
                      owner_id: Optional[str] = None, due_on: Optional[str] = None,
                      property_id: Optional[str] = None, create_crm_task: bool = False) -> str:
    """Turn a message into a tracked action (task/approval/verification/request), optional CRM task."""
    linked = None
    if create_crm_task:
        task = Task(title=title, description=detail, assigned_agent_id=owner_id,
                    related_type="property" if property_id else "conversation",
                    related_id=property_id or conversation_id, due_date=due_on, priority="medium")
        tasks_db.append(task)
        linked = task.id
    return dump(messaging.create_action(
        conversation_id, created_by, title, kind=kind, message_id=message_id, detail=detail,
        owner_id=owner_id, due_on=due_on, property_id=property_id, linked_task_id=linked))


@mcp.tool()
def msg_actions(user_id: str, conversation_id: Optional[str] = None,
                owner_id: Optional[str] = None, status: Optional[str] = None,
                kind: Optional[str] = None, overdue_only: bool = False) -> str:
    """List tracked actions the user can see (filter by conversation, owner, status, kind)."""
    return dump(messaging.list_actions(user_id, conversation_id=conversation_id, owner_id=owner_id,
                                       status=status, kind=kind, overdue_only=overdue_only))


@mcp.tool()
def msg_action(action_id: str, user_id: str) -> str:
    """One tracked action with its updates and overdue flag."""
    return dump(messaging.get_action(action_id, user_id))


@mcp.tool()
def msg_update_action(action_id: str, user_id: str, status: Optional[str] = None,
                      owner_id: Optional[str] = None, due_on: Optional[str] = None,
                      note: Optional[str] = None) -> str:
    """Update an action's status, owner or due date and add a note."""
    return dump(messaging.update_action(action_id, user_id, status=status, owner_id=owner_id,
                                        due_on=due_on, note=note))


@mcp.tool()
def msg_complete_action(action_id: str, user_id: str, note: Optional[str] = None) -> str:
    """Mark an action done and notify its creator."""
    return dump(messaging.complete_action(action_id, user_id, note))


@mcp.tool()
def msg_notifications(user_id: str, unread_only: bool = False, category: Optional[str] = None,
                      limit: int = 50) -> str:
    """A user's notifications (queue + delivered) with unread count."""
    return dump(messaging.notifications(user_id, unread_only=unread_only, category=category, limit=limit))


@mcp.tool()
def msg_read_notification(notification_id: str, user_id: str) -> str:
    """Mark one notification read."""
    return dump(messaging.read_notification(notification_id, user_id))


@mcp.tool()
def msg_mark_all_notifications_read(user_id: str) -> str:
    """Mark every notification read for a user."""
    return dump(messaging.mark_all_notifications_read(user_id))


@mcp.tool()
def msg_dispatch(user_id: Optional[str] = None, limit: int = 200, force: bool = False) -> str:
    """Drain the notification queue into the outbox (the background-worker seam)."""
    return dump(messaging.dispatch_pending(user_id=user_id, limit=limit, force=force))


@mcp.tool()
def msg_outbox(channel: Optional[str] = None, user_id: Optional[str] = None,
               limit: int = 100) -> str:
    """Delivered notifications with rendered e-mail and Telegram payloads."""
    return dump(messaging.outbox(channel=channel, user_id=user_id, limit=limit))


@mcp.tool()
def msg_unread_summary(user_id: str) -> str:
    """Combined unread picture: conversations, mentions, notifications and open actions."""
    return dump(messaging.unread_summary(user_id))


@mcp.tool()
def msg_telegram_link_code(user_id: str) -> str:
    """Mint a single-use /start code so a user can link their Telegram chat."""
    return dump(messaging.telegram_link_code(user_id))


@mcp.tool()
def msg_telegram_link(user_id: str, chat_id: str, username: Optional[str] = None,
                      categories: Optional[List[str]] = None) -> str:
    """Opt a user in: bind a Telegram chat id and the allowed notification categories."""
    return dump(messaging.telegram_link(user_id, chat_id, username=username, categories=categories))


@mcp.tool()
def msg_telegram_unlink(user_id: str) -> str:
    """Unlink a user's Telegram chat and disable Telegram alerts."""
    return dump(messaging.telegram_unlink(user_id))


@mcp.tool()
def msg_telegram_links(active_only: bool = True) -> str:
    """Every Telegram link (optionally only the active ones)."""
    return dump(messaging.telegram_links(active_only))


@mcp.tool()
def msg_telegram_status(user_id: str) -> str:
    """Whether a user is linked to Telegram, which categories and the bot name."""
    return dump(messaging.telegram_status(user_id))


@mcp.tool()
def msg_telegram_update(update: Dict[str, Any]) -> str:
    """Process one inbound Telegram bot update (/start, /stop, /mute, /digest, /status)."""
    return dump(messaging.telegram_handle_update(update))


@mcp.tool()
def msg_telegram_alert(user_id: str, text: str, priority: str = "normal",
                       conversation_id: Optional[str] = None,
                       message_id: Optional[str] = None) -> str:
    """Queue and dispatch a sanitised alert (short text + deep link, never documents)."""
    return dump(messaging.telegram_alert(user_id, text, priority=priority,
                                         conversation_id=conversation_id, message_id=message_id))


@mcp.tool()
def msg_audit(limit: int = 100, action: Optional[str] = None, actor_id: Optional[str] = None,
              target_type: Optional[str] = None) -> str:
    """The messaging audit trail of important actions (access, files, moderation)."""
    return dump(messaging.list_audit(limit=limit, action=action, actor_id=actor_id,
                                     target_type=target_type))


@mcp.tool()
def msg_retention_report() -> str:
    """Per-conversation retention picture: messages, pins and purgeable counts."""
    return dump(messaging.retention_report())


@mcp.tool()
def msg_purge_retention(dry_run: bool = True, retention_days: Optional[int] = None,
                        actor_id: Optional[str] = None) -> str:
    """Apply the retention policy (soft-delete past the window; pinned exempt)."""
    return dump(messaging.purge_retention(dry_run=dry_run, retention_days=retention_days,
                                          actor_id=actor_id))


@mcp.tool()
def msg_report_message(message_id: str, reporter_id: str, reason: str = "other",
                       detail: Optional[str] = None) -> str:
    """Report a message (spam, abuse, confidential leak, off-topic)."""
    return dump(messaging.report_message(message_id, reporter_id, reason=reason, detail=detail))


@mcp.tool()
def msg_reports(status: Optional[str] = None, limit: int = 100) -> str:
    """Message reports and their status (spam-control queue)."""
    return dump(messaging.list_reports(status=status, limit=limit))


@mcp.tool()
def msg_moderate_report(report_id: str, actor_id: str, action: str,
                        note: Optional[str] = None) -> str:
    """Resolve a report: dismiss, delete the message, mute the author or escalate."""
    return dump(messaging.moderate_report(report_id, actor_id, action, note=note))


@mcp.tool()
def msg_conversation_digest(conversation_id: str, user_id: str, days: int = 7) -> str:
    """Recent-activity digest for a conversation over a window."""
    return dump(messaging.conversation_digest(conversation_id, user_id, days=days))


@mcp.tool()
def msg_statistics() -> str:
    """Aggregate messaging statistics for the portal dashboard."""
    return dump(messaging.messaging_statistics())


def _messaging_activity_svg(rows: List[Dict[str, Any]]) -> str:
    """Compact horizontal bars for the busiest conversations."""
    if not rows:
        return '<p style="color:var(--muted)">No conversations yet.</p>'
    top = sorted(rows, key=lambda r: r.get("messages", 0), reverse=True)[:10]
    width = max([r.get("messages", 0) for r in top] + [1])
    out = ["<div style='display:flex;flex-direction:column;gap:8px'>"]
    for r in top:
        pct = 100.0 * r.get("messages", 0) / width
        out.append(
            "<div style='display:flex;align-items:center;gap:10px;font-size:13px'>"
            f"<div style='width:230px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap'>"
            f"{r.get('title','')}</div>"
            f"<svg width='260' height='14'><rect width='260' height='14' rx='3' fill='#e5e7eb'/>"
            f"<rect width='{260 * pct / 100.0:.1f}' height='14' rx='3' fill='#2563eb'/></svg>"
            f"<span style='width:60px;text-align:right'>{r.get('messages',0)}</span>"
            f"<span style='width:110px;color:var(--muted)'>{r.get('kind','')}</span>"
            "</div>")
    out.append("</div>")
    return "".join(out)


def messaging_portal_html(lang: str = "en", theme: str = "auto") -> str:
    """The Team Messaging & Notifications page as printable HTML."""
    ov = messaging.messaging_overview()
    stats = messaging.messaging_statistics()
    channels = messaging.messaging_channels()
    conversation_rows = []
    for conv in sorted(messaging.conversations_db, key=lambda c: c.message_count, reverse=True)[:25]:
        conversation_rows.append([conv.id[:14], conv.kind, conv.title,
                                  str(len(messaging.members_of(conv.id))), str(conv.message_count),
                                  conv.last_message_at or conv.created_at])
    audit_rows = [[e.at, e.action, messaging.display_name_for(e.actor_id), e.detail or ""]
                  for e in sorted(messaging.audit_db, key=lambda e: e.at, reverse=True)[:20]]
    outbox_rows = [[o.created_at, o.channel, messaging.display_name_for(o.user_id),
                    (o.subject or "")[:60]] for o in sorted(messaging.outbox_db,
                                                            key=lambda o: o.created_at, reverse=True)[:20]]
    sections = [
        {"kind": "cards", "heading": "Workspace", "items": [
            ("Team profiles", str(stats["profiles"]), f"{stats['online']} online"),
            ("Conversations", str(stats["conversations"]),
             ", ".join(f"{k} {v}" for k, v in stats["by_kind"].items()) or "none yet"),
            ("Live messages", str(stats["messages_live"]), f"{stats['messages']} total"),
            ("Attachments", str(stats["attachments"]), f"{stats['attachments_confidential']} confidential"),
            ("Open actions", str(stats["actions_open"]), f"{stats['actions']} total"),
            ("Telegram opt-in", str(stats["telegram_opt_in"]), "optional alert channel"),
        ]},
        {"kind": "html", "heading": "Busiest conversations",
         "html": _messaging_activity_svg([
             {"title": c.title, "messages": c.message_count, "kind": c.kind}
             for c in sorted(messaging.conversations_db, key=lambda c: c.message_count, reverse=True)
         ])},
        {"kind": "table", "heading": "Conversations",
         "columns": ["Id", "Kind", "Title", "Members", "Messages", "Last activity"],
         "rows": conversation_rows},
        {"kind": "table", "heading": "Channels",
         "columns": ["Key", "Channel", "Purpose", "Restricted"],
         "rows": [[c["key"], c["name"], c["purpose"], "yes" if c["restricted"] else "no"]
                  for c in channels["channels"]]},
        {"kind": "table", "heading": "Notification categories & delivery",
         "columns": ["Category", "Delivered via", "Urgent"],
         "rows": [[k, ", ".join(v["channels"]), "yes" if v["urgent"] else "no"]
                  for k, v in messaging.NOTIFICATION_CATEGORIES.items()]},
        {"kind": "table", "heading": "Notification outbox",
         "columns": ["At", "Channel", "Recipient", "Subject"], "rows": outbox_rows},
        {"kind": "table", "heading": "Audit trail",
         "columns": ["At", "Action", "Actor", "Detail"], "rows": audit_rows},
        {"kind": "text", "heading": "Rollout", "text": "\n".join(ov["rollout"])},
        {"kind": "text", "heading": "Storage & delivery note", "text": ov["storage_note"]},
    ]
    return gis.build_report_html(title="Team Messaging & Notifications",
                                 subtitle="Conversations tied to properties, plans, customers and tasks",
                                 sections=sections, ticker_html=_portal_ticker(lang),
                                 lang=lang, theme=theme)


@mcp.tool()
def msg_portal(lang: str = "en", theme: str = "auto") -> str:
    """The Team Messaging & Notifications wing as a printable HTML page."""
    return messaging_portal_html(lang, theme)


@mcp.resource("messaging://overview", name="Messaging overview",
              description="Workspace config, channels, categories and counts.")
def res_msg_overview() -> str:
    return dump(messaging.messaging_overview())


@mcp.resource("messaging://channels", name="Team channels",
              description="Default team channels with purpose and access rules.")
def res_msg_channels() -> str:
    return dump(messaging.messaging_channels())


@mcp.resource("messaging://categories", name="Notification categories",
              description="Notification categories, delivery channels and urgency.")
def res_msg_categories() -> str:
    return dump(messaging.notification_categories())


@mcp.resource("messaging://profiles", name="Messaging directory",
              description="Team messaging profiles with presence and unread counts.")
def res_msg_profiles() -> str:
    return dump(messaging.list_profiles())


@mcp.resource("messaging://outbox", name="Notification outbox",
              description="Delivered notifications with rendered e-mail/Telegram payloads.")
def res_msg_outbox() -> str:
    return dump(messaging.outbox(limit=50))


@mcp.resource("messaging://audit", name="Messaging audit",
              description="Audit trail of messaging actions.")
def res_msg_audit() -> str:
    return dump(messaging.list_audit(limit=100))


@mcp.resource("messaging://reports", name="Message reports",
              description="Message reports and moderation status.")
def res_msg_reports() -> str:
    return dump(messaging.list_reports())


@mcp.resource("messaging://statistics", name="Messaging statistics",
              description="Aggregate messaging statistics.")
def res_msg_statistics() -> str:
    return dump(messaging.messaging_statistics())


@mcp.resource("messaging://conversation/{conversation_id}", name="Conversation",
              description="One conversation (members, pins, context) by id.")
def res_msg_conversation(conversation_id: str) -> str:
    conv = messaging._get(messaging.conversations_db, "id", conversation_id)
    if conv is None:
        return dump({"error": f"conversation '{conversation_id}' not found"})
    view = messaging.conversation_view(conv)
    view["context"] = messaging.conversation_context(conversation_id)
    return dump({"conversation": view})


@mcp.resource("messaging://unread/{user_id}", name="Unread summary",
              description="Unread conversations, mentions, notifications and open actions for a user.")
def res_msg_unread(user_id: str) -> str:
    return dump(messaging.unread_summary(user_id))


@mcp.prompt(name="messaging_briefing_prompt",
            description="Brief a team member on their messaging workspace and open items.")
def prompt_messaging_briefing(user_id: str = "", focus: str = "everything urgent") -> str:
    return (
        "You are the Arz-e-Pak team-workspace assistant.\n"
        + (f"User: {user_id}.\n" if user_id else "Scope: whole team.\n")
        + f"Focus: {focus}.\n"
        "1. msg_unread_summary (or msg_unread) for unread counts, mentions and open actions.\n"
        "2. msg_conversations to list active threads; msg_summary on the busiest ones.\n"
        "3. msg_actions(overdue_only=true) for slipping work; msg_telegram_* only for elective alerts.\n"
        "4. Produce a short briefing: what needs a reply, what is overdue, what can wait. "
        "Never quote confidential attachment content in summary e-mails or Telegram text."
    )


@mcp.prompt(name="messaging_thread_digest_prompt",
            description="Summarise a conversation thread and extract its action items.")
def prompt_messaging_digest(conversation_id: str = "", days: int = 7) -> str:
    return (
        "You are summarising an internal Arz-e-Pak conversation"
        + (f" ({conversation_id})" if conversation_id else "") + f" over the last {days} days.\n"
        "1. msg_conversation_digest for activity; msg_summarize for topics and salient lines.\n"
        "2. msg_action_items to surface requests and assignments; create only what the team confirms.\n"
        "3. Reply with: decisions made, who owns what by when, and any unresolved question."
    )


@mcp.prompt(name="messaging_escalation_prompt",
            description="Draft a formal e-mail escalation for an unresolved internal issue.")
def prompt_messaging_escalation(conversation_id: str = "", issue: str = "") -> str:
    return (
        "You are drafting a formal escalation e-mail for an internal Arz-e-Pak issue.\n"
        + (f"Source conversation: {conversation_id}.\n" if conversation_id else "")
        + (f"Issue: {issue}.\n" if issue else "")
        + "1. msg_summarize + msg_actions to gather the facts and the current owner.\n"
        "2. msg_create_action(kind='approval' or 'task') to record the escalation in the portal.\n"
        "3. Produce a concise e-mail (subject, context, impact, requested decision, deadline) "
        "and note that it will be dispatched through the notification outbox."
    )





# ============================================================
# ====== AGENTIC OS · TRANSACTIONS · INTELLIGENCE ============
# ====== LEASING · MARKETING · COMMERCIALIZATION =============
# ============================================================
#
# Everything below reuses the framework-free domain modules (agents,
# transactions, intelligence, leasing, marketing, commercial) so the MCP tools
# and the REST layer share one implementation.


def _scheme_label(scheme_id: Optional[str]) -> Optional[str]:
    s = find_scheme(scheme_id)
    return s.name if s else None


def _property_candidate(p: Property) -> Dict[str, Any]:
    return {
        "id": p.id, "title": p.title, "price": p.price or 0.0, "category": p.category,
        "use_type": p.use_type, "city": city_name(p.city_id), "scheme": _scheme_label(p.scheme_id),
        "covered_area": p.covered_area, "plot_area": p.plot_area, "marla_area": p.marla_area,
        "bedrooms": p.bedrooms, "age_years": 0, "status": p.status,
    }


def _resolve_commute_point(text: Optional[str]) -> Optional[Tuple[float, float]]:
    if not text:
        return None
    t = text.strip().lower()
    for poi in pois_db:
        if t and t in poi.name.lower():
            return (poi.latitude, poi.longitude)
    return None


def _candidate_context(req: Dict[str, Any], p: Property,
                       commute_point: Optional[Tuple[float, float]] = None) -> Dict[str, Any]:
    """Derive GIS context (amenities, schools, commute) for one property."""
    ctx: Dict[str, Any] = {}
    if p.latitude is None or p.longitude is None:
        return ctx
    counts: Dict[str, int] = {}
    for poi in pois_db:
        d = haversine_km(p.latitude, p.longitude, poi.latitude, poi.longitude)
        if d <= 2.0:
            counts[poi.category] = counts.get(poi.category, 0) + 1
    ctx["amenities_score"] = min(100.0, 30.0 + sum(counts.values()) * 4.0)
    ctx["schools_score"] = min(100.0, 45.0 + counts.get("education", 0) * 15.0)
    ctx["safety_score"] = min(100.0, 50.0 + counts.get("government", 0) * 10.0
                              + counts.get("health", 0) * 5.0)
    ctx["poi_counts"] = counts
    dest = commute_point
    if dest is None:
        c = find_city(p.city_id)
        dest = (c.latitude, c.longitude) if (c and c.latitude is not None) else None
    if dest:
        km = haversine_km(p.latitude, p.longitude, dest[0], dest[1]) * 1.3
        ctx["commute_km"] = round(km, 2)
        ctx["commute_minutes"] = round(km / 25.0 * 60.0, 1)  # 25 km/h urban average
    return ctx


def _buyer_recommend_impl(text: Optional[str] = None, requirement: Optional[Dict[str, Any]] = None,
                          limit: int = 8, city: Optional[str] = None, category: Optional[str] = None,
                          use_type: Optional[str] = None,
                          max_price: Optional[float] = None) -> Dict[str, Any]:
    req = dict(requirement) if requirement else intelligence.parse_requirement(
        text or "", known_cities=[c.name for c in cities_db])
    if "error" in req:
        return req
    rows = list(properties_db)
    if city:
        c = resolve_city(city)
        if c:
            rows = [p for p in rows if p.city_id == c.id]
    if category:
        rows = [p for p in rows if p.category == category]
    if use_type:
        rows = [p for p in rows if p.use_type == use_type]
    if max_price:
        rows = [p for p in rows if (p.price or 0.0) <= max_price]
    commute_point = _resolve_commute_point(req.get("commute_destination"))
    contexts: Dict[str, Dict[str, Any]] = {}
    cands: List[Dict[str, Any]] = []
    for p in rows:
        cands.append(_property_candidate(p))
        contexts[p.id] = _candidate_context(req, p, commute_point)
    ranked = intelligence.rank_candidates(req, cands, contexts, limit=limit)
    ranked["commute_reference"] = req.get("commute_destination")
    return ranked


def _lead_features(l: Lead) -> Dict[str, Any]:
    interactions = [i for i in interactions_db if i.entity_type == "lead" and i.entity_id == l.id]
    last = max((i.occurred_at for i in interactions), default=l.updated_at)
    days = max(0.0, float((datetime.now() - last).days))
    return {
        "owns": l.status not in ("new",), "tenure_years": 0.0,
        "engagement_score": l.score or 40, "financial_ready": bool(l.budget_max),
        "market_heat": 0.6, "days_since_contact": days,
    }


def _smart_action_signals() -> List[Dict[str, Any]]:
    """Assemble prioritised signals from across the portal for the Smart Actions list."""
    today = datetime.now().date()
    signals: List[Dict[str, Any]] = []
    for d in deals_db:
        if d.expected_close_date and d.stage not in ("closed_won", "closed_lost"):
            try:
                due = datetime.strptime(d.expected_close_date, "%Y-%m-%d")
            except ValueError:
                continue
            hours = (due - datetime.now()).total_seconds() / 3600
            if hours <= 24 * 14:
                signals.append({"kind": "deal", "title": f"Deal closing: {d.title}",
                                "entity_type": "deal", "entity_id": d.id, "due_in_hours": round(hours, 1),
                                "impact": 5, "urgency": 4,
                                "reason": f"stage {d.stage}, {d.probability}% probability",
                                "suggested_agent": "transaction_agent"})
    for t in tasks_db:
        if t.status in ("open", "in_progress") and t.due_date:
            try:
                due = datetime.strptime(t.due_date, "%Y-%m-%d")
            except ValueError:
                continue
            hours = (due - datetime.now()).total_seconds() / 3600
            if hours <= 24 * 7:
                signals.append({"kind": "task", "title": t.title, "entity_type": "task",
                                "entity_id": t.id, "due_in_hours": round(hours, 1),
                                "impact": {"urgent": 5, "high": 4}.get(t.priority, 3), "urgency": 4,
                                "reason": f"{t.priority} priority", "suggested_agent": "crm_agent"})
    for tx in transactions.transactions_db:
        if tx.status != "open":
            continue
        prog = transactions.transaction_progress(tx.id)
        for od in prog.get("overdue", []):
            signals.append({"kind": "milestone", "title": f"{tx.code}: {od['name']} overdue",
                            "entity_type": "transaction", "entity_id": tx.id,
                            "due_in_hours": -abs(od["days_late"]) * 24,
                            "impact": 5 if od["blocking"] else 3, "urgency": 5,
                            "reason": f"{od['days_late']} days late",
                            "suggested_agent": "transaction_agent"})
        nd = prog.get("next_deadline")
        if nd and nd["days_left"] <= 7:
            signals.append({"kind": "milestone", "title": f"{tx.code}: {nd['name']} due",
                            "entity_type": "transaction", "entity_id": tx.id,
                            "due_in_hours": nd["days_left"] * 24, "impact": 4, "urgency": 3,
                            "reason": f"{nd['days_left']} days left",
                            "suggested_agent": "transaction_agent"})
    for lease in accounting.leases_db:
        if lease.status != "active":
            continue
        if lease.end_date:
            days = (lease.end_date - today).days
        else:
            days = (lease.start_date - today).days + 365
        if days <= 90:
            signals.append({"kind": "renewal", "title": f"Lease renewal: {lease.tenant}",
                            "entity_type": "lease", "entity_id": lease.id, "due_in_hours": days * 24,
                            "impact": 4, "urgency": 3, "reason": f"{days} days to expiry",
                            "suggested_agent": "renewal_agent"})
    for inv in accounting.invoices_db:
        if inv.balance and inv.balance > 0 and inv.due_date and inv.due_date < today:
            signals.append({"kind": "collection",
                            "title": f"Overdue invoice {inv.number} ({inv.counterparty})",
                            "entity_type": "invoice", "entity_id": inv.id,
                            "due_in_hours": -((today - inv.due_date).days) * 24,
                            "impact": 4, "urgency": 4, "reason": f"balance {inv.balance:,.0f}",
                            "suggested_agent": "accounting_agent"})
    for l in leads_db:
        ml = agents.move_likelihood(_lead_features(l))
        if ml["band"] in ("very_high", "high"):
            signals.append({"kind": "lead", "title": f"Warm lead: {l.name}",
                            "entity_type": "lead", "entity_id": l.id, "due_in_hours": 24,
                            "impact": 4, "urgency": 3, "reason": ml["reasons"][0],
                            "suggested_agent": "crm_agent"})
    for w in maintenance.work_orders_db:
        if w.status == "open" and w.priority in ("urgent", "soon"):
            signals.append({"kind": "maintenance", "title": f"Work order: {w.title}",
                            "entity_type": "work_order", "entity_id": w.id,
                            "due_in_hours": 12 if w.priority == "urgent" else 48,
                            "impact": 4, "urgency": 4, "reason": f"{w.priority} · {w.component}",
                            "suggested_agent": "maintenance_triage_agent"})
    return signals


def _seller_cma_impl(property_id: str, comp_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    subject = find_property(property_id)
    if not subject:
        return {"error": f"Unknown property: {property_id}"}
    comps = [p for p in properties_db if p.id != subject.id and p.category == subject.category
             and p.city_id == subject.city_id and p.status in ("active", "sold")]
    if comp_ids:
        wanted = set(comp_ids)
        comps = [p for p in properties_db if p.id in wanted]
    subject_dict = {"title": subject.title, "price": subject.price,
                    "covered_area": subject.covered_area or subject.plot_area,
                    "plot_area": subject.plot_area, "age_years": 0,
                    "condition_score": 3, "location_score": 3}
    comp_dicts = [{"id": c.id, "title": c.title, "price": c.price,
                   "covered_area": c.covered_area or c.plot_area, "plot_area": c.plot_area,
                   "age_years": 0, "condition_score": 3, "location_score": 3} for c in comps[:12]]
    out = intelligence.pricing_cma(subject_dict, comp_dicts, market={"average_dom": 45})
    out["subject_id"] = subject.id
    return out


def _screen_over_properties(criteria: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    crit = dict(criteria or {})
    rows = list(properties_db)
    if crit.get("city"):
        c = resolve_city(crit["city"])
        if c:
            rows = [p for p in rows if p.city_id == c.id]
    if crit.get("category"):
        rows = [p for p in rows if p.category == crit["category"]]
    cands = []
    for p in rows:
        cands.append({
            "id": p.id, "title": p.title, "city": city_name(p.city_id), "category": p.category,
            "purchase_price": p.price or 0.0,
            "monthly_rent": round((p.price or 0.0) * (crit.get("rental_yield") or 0.045) / 12.0, 2),
            "down_payment_share": crit.get("down_payment_share", 0.25),
            "loan_rate": crit.get("loan_rate", 0.16), "loan_years": crit.get("loan_years", 20),
            "hold_years": crit.get("hold_years", 10),
        })
    return intelligence.screen_investments(cands, crit)


def _agent_tool_dispatch(name: str, ctx: Dict[str, Any]) -> Any:
    """Execute a real portal function for an agent step — the MCP-for-brokers loop."""
    text = ctx.get("text") or ctx.get("objective") or ""
    if name in ("buyer_parse_requirement",):
        return intelligence.parse_requirement(text, known_cities=[c.name for c in cities_db])
    if name in ("buyer_recommend", "recommend_property"):
        return _buyer_recommend_impl(text=text, limit=5)
    if name in ("buyer_anomaly_scan", "anomaly_scan"):
        return intelligence.anomaly_scan([_property_candidate(p) for p in properties_db])
    if name in ("buyer_affordability", "affordability"):
        price = float(ctx.get("price") or ctx.get("budget_max") or 0.0)
        return intelligence.affordability(price, monthly_income=ctx.get("monthly_income"))
    if name in ("seller_cma", "pricing_cma"):
        pid = ctx.get("property_id") or next((p.id for p in properties_db), None)
        return _seller_cma_impl(pid) if pid else {"error": "no property"}
    if name == "seller_net_proceeds":
        return intelligence.net_proceeds(float(ctx.get("price") or 0.0),
                                         mortgage_payoff=float(ctx.get("mortgage_payoff") or 0.0))
    if name == "seller_marketing_assets":
        pid = ctx.get("property_id")
        p = find_property(pid) if pid else (properties_db[0] if properties_db else None)
        if not p:
            return {"error": "no property"}
        return intelligence.generate_listing_assets({
            "id": p.id, "title": p.title, "city": city_name(p.city_id),
            "scheme": _scheme_label(p.scheme_id), "price": p.price, "covered_area": p.covered_area,
            "bedrooms": p.bedrooms, "category": p.category}, lang=ctx.get("lang", "en"))
    if name in ("investment_screen", "screen_investments"):
        return _screen_over_properties(ctx.get("criteria"))
    if name == "investment_underwrite":
        return intelligence.underwrite(ctx)
    if name == "investment_portfolio_alerts":
        return intelligence.portfolio_alerts(ctx.get("holdings") or [], ctx.get("signals"))
    if name in ("marketing_qualify_lead",):
        lead = next((l for l in leads_db if l.id == ctx.get("lead_id")), None)
        ml = marketing.MarketingLead(name=lead.name if lead else ctx.get("name", ""),
                                     channel=(lead.source if lead else "website"),
                                     budget_max=(lead.budget_max if lead else None),
                                     city=(city_name(lead.city_id) if lead else None),
                                     engagement=(lead.score if lead else 40))
        return marketing.qualify_lead(ml)
    if name in ("marketing_route_lead",):
        lead = next((l for l in leads_db if l.id == ctx.get("lead_id")), None)
        ml = marketing.MarketingLead(name=lead.name if lead else "", channel=(lead.source if lead else "website"),
                                     city=(city_name(lead.city_id) if lead else None))
        marketing.qualify_lead(ml)
        return marketing.route_lead(ml)
    if name in ("marketing_reengagement", "reengagement"):
        return marketing.reengagement_candidates()
    if name in ("marketing_generate_content", "campaign_plan"):
        if name == "campaign_plan":
            return marketing.campaign_plan(ctx.get("objective", "campaign"),
                                           float(ctx.get("budget") or 100000.0),
                                           ctx.get("channels") or ["whatsapp", "website"]).model_dump()
        pid = ctx.get("property_id")
        p = find_property(pid) if pid else (properties_db[0] if properties_db else None)
        listing = {"id": p.id, "title": p.title, "city": city_name(p.city_id), "price": p.price} if p else {}
        return marketing.generate_content(ctx.get("kind", "market_report"), listing=listing).model_dump()
    if name in ("leasing_inquiry",):
        unit = next((u for u in leasing.units_db if u.id == ctx.get("unit_id")), None) \
            or (leasing.units_db[0] if leasing.units_db else None)
        return leasing.handle_inquiry(unit, text, channel=ctx.get("channel", "web_chat"),
                                      lang=ctx.get("lang", "en")).model_dump()
    if name == "leasing_screen_application":
        unit = next((u for u in leasing.units_db if u.id == ctx.get("unit_id")), None)
        app = leasing.Application(applicant=ctx.get("applicant", "applicant"),
                                  monthly_income=float(ctx.get("monthly_income") or 0.0))
        return leasing.screen_application(app, unit)
    if name == "rent_floor":
        return leasing.rent_floor(float(ctx.get("monthly_holding_cost") or 0.0))
    if name in ("leasing_renewals", "renewal"):
        rows = []
        for lease in accounting.leases_db:
            days = (lease.end_date - datetime.now().date()).days if lease.end_date else 365
            rows.append(leasing.renewal_recommendation(
                {"rent_amount": lease.rent_amount, "days_to_expiry": days},
                {"market_rent": lease.rent_amount * 1.08}))
        return {"count": len(rows), "renewals": rows}
    if name in ("smart_actions",):
        return agents.prioritise_actions(_smart_action_signals(), limit=10)
    if name in ("move_likelihood",):
        lead = next((l for l in leads_db if l.id == ctx.get("lead_id")), None)
        return agents.move_likelihood(_lead_features(lead) if lead else ctx)
    if name == "score_seller_intent":
        cid = ctx.get("contact_id") or ctx.get("lead_id")
        if cid and _contact_from_id(cid):
            return json.loads(score_seller_intent(cid))
        return agents.seller_intent_score(ctx)
    if name in ("transaction_terms_extract",):
        return transactions.extract_terms(ctx.get("document_text") or text)
    if name == "transaction_deadlines":
        return transactions.upcoming_deadlines(int(ctx.get("horizon_days") or 14))
    if name == "transaction_progress":
        return transactions.transaction_progress(ctx.get("transaction_id") or ctx.get("tx_id"))
    if name == "transaction_verify_signatures":
        return transactions.verify_signatures(ctx.get("transaction_id") or "")
    if name == "transaction_create":
        tx = transactions.create_transaction(price=float(ctx.get("price") or 0.0),
                                             property_title=ctx.get("property_title"),
                                             transaction_type=ctx.get("transaction_type", "sale"))
        return transactions.txn_view(tx)
    if name == "create_offer":
        return transactions.add_offer(ctx.get("transaction_id") or "", float(ctx.get("price") or 0.0))
    if name in ("commission_projection", "get_commission_projection"):
        return json.loads(get_commission_projection(agent_id=ctx.get("agent_id")))
    if name == "accounting_snapshot":
        pid = ctx.get("property_id")
        if pid and find_property(pid):
            return json.loads(get_accounting_snapshot(pid))
        return accounting.accounting_dashboard()
    if name in ("market_intelligence", "get_market_intelligence"):
        return json.loads(get_market_intelligence(region=ctx.get("region") or ctx.get("city")))
    if name in ("gis_score", "analyze_property_gis"):
        return _gis_score_impl(ctx.get("property_id"), ctx.get("address"),
                               ctx.get("commute_destination") or ctx.get("destination"))
    if name == "search_contacts":
        q = ctx.get("query") or ctx.get("name")
        return json.loads(search_contacts(query=q or None))
    if name == "compliance_check":
        pid = ctx.get("property_id")
        p = find_property(pid) if pid else None
        findings = []
        if p and not p.latitude:
            findings.append("missing geo-coordinates")
        if p and p.price <= 0:
            findings.append("missing price")
        return {"property_id": pid, "passed": not findings, "findings": findings}
    if name in ("construction_advisory", "construction_estimate", "construction_impact"):
        if name == "construction_advisory":
            return construction.construction_advisory(
                ctx.get("building_type", "house"), ctx.get("quality_tier", "standard"),
                ctx.get("system", "rcc_frame"), ctx.get("city"))
        if name == "construction_estimate":
            return construction.estimate_construction(
                float(ctx.get("covered_area") or 2000.0),
                building_type=ctx.get("building_type", "house"),
                quality_tier=ctx.get("quality_tier", "standard"), city=ctx.get("city"))
        return construction.construction_impact(
            float(ctx.get("property_value") or 20000000.0),
            building_type=ctx.get("building_type", "house"),
            quality_tier=ctx.get("quality_tier", "standard")).get("impact", {})
    if name in ("maintenance_defect",):
        return {"defect": ctx.get("defect"), "catalogue": maintenance.DEFECT_CATALOGUE[:1]}
    if name == "maintenance_repair_estimate":
        return maintenance.repair_estimate(ctx.get("defect", "roof_seepage"),
                                           quantity=float(ctx.get("quantity") or 1.0), city=ctx.get("city"))
    if name in ("maintenance_work_order_create",):
        wo = maintenance.WorkOrder(title=ctx.get("title", "Auto work order"),
                                   component=ctx.get("component", "general"),
                                   defect=ctx.get("defect", "other"),
                                   priority=ctx.get("priority", "routine"))
        maintenance.work_orders_db.append(wo)
        return wo.model_dump()
    if name in ("revenue_share",):
        return transactions.revenue_share(float(ctx.get("commission_gross") or 0.0))
    if name in ("bill_account",):
        return commercial.bill_account(ctx.get("account", "brokerco"))
    if name in ("outreach_draft",):
        return {"draft": f"Hi {ctx.get('name', 'there')}, following up on your property search — "
                         f"shall I send 3 new matches?"}
    if name == "create_listing_draft":
        pid = ctx.get("property_id")
        if pid and find_property(pid):
            return json.loads(create_listing_draft(pid, lang=ctx.get("lang", "en")))
        return {"note": "create_listing_draft queued for human confirmation", "status": "pending"}
    if name == "schedule_viewing":
        return {"note": "schedule_viewing queued for human confirmation", "status": "pending"}
    return {"note": f"no dispatcher binding for '{name}' — step recorded for the audit trail",
            "dispatched": False}


@mcp.tool()
def agents_overview() -> str:
    """Counts, products, autonomy mix and run activity across the Agentic OS."""
    return dump(agents.agentic_overview())


@mcp.tool()
def agents_catalog(category: Optional[str] = None, product: Optional[str] = None,
                   priority: Optional[str] = None, autonomy: Optional[str] = None) -> str:
    """The agent catalogue: 8 roadmap product agents plus specialist sub-agents.

    Each agent lists its category, autonomy level, bound tools, inputs, outputs,
    hand-offs and KPIs. Filter by ``category`` (buyer_side/seller_side/broker/
    investor/landlord/marketing/platform), ``product``, ``priority`` or ``autonomy``.
    """
    rows = agents.agent_catalog(category=category, product=product, priority=priority, autonomy=autonomy)
    return dump({"count": len(rows), "agents": rows,
                 "categories": sorted({a["category"] for a in agents.AGENTS}),
                 "products": sorted({a["product"] for a in agents.AGENTS if a["product"]})})


@mcp.tool()
def agent_get(key: str) -> str:
    """One agent's full definition by key (e.g. ``conversational_buyer_agent``)."""
    row = agents.find_agent(key)
    if not row:
        return dump({"error": f"Unknown agent: {key}", "keys": [a["key"] for a in agents.AGENTS]})
    return dump(agents.agent_view(row))


@mcp.tool()
def agent_products(priority: Optional[str] = None) -> str:
    """The eight roadmap products, their priority (P0–P2) and their agent modules."""
    return dump({"count": len(agents.PRODUCTS), "products": agents.agent_products(priority)})


@mcp.tool()
def agent_plan(agent_key: str, objective: str = "", subject_type: Optional[str] = None,
               subject_id: Optional[str] = None) -> str:
    """Plan (but do not execute) an agent run: the explicit ``intake → tools → review → deliver`` steps."""
    return dump(agents.plan_run(agent_key, objective, subject_type=subject_type, subject_id=subject_id))


@mcp.tool()
def agent_run(agent_key: str, objective: str = "", text: Optional[str] = None,
              subject_type: Optional[str] = None, subject_id: Optional[str] = None,
              approve: bool = True, extra: Optional[Dict[str, Any]] = None) -> str:
    """Execute an agent run against the live portal.

    The run engine calls the real portal functions bound to the agent, recording every
    step. With ``approve=False`` the run pauses at the human-approval gate; finish it
    with ``agent_approve``. This is the "MCP for brokers" loop: the same tools an
    external AI client would call.
    """
    ctx = dict(extra or {})
    if text:
        ctx["text"] = text
    if subject_id:
        ctx.setdefault("property_id" if subject_type == "property" else
                       "transaction_id" if subject_type == "transaction" else "lead_id", subject_id)
    return dump(agents.run_agent(agent_key, objective, dispatch=_agent_tool_dispatch, context=ctx,
                                 subject_type=subject_type, subject_id=subject_id, approve=approve))


@mcp.tool()
def agent_runs(agent_key: Optional[str] = None, status: Optional[str] = None) -> str:
    """Recorded agent runs (the audit trail), optionally filtered by agent or status."""
    rows = agents.list_runs(agent_key, status)
    return dump({"count": len(rows), "runs": [agents.run_view(r) for r in rows]})


@mcp.tool()
def agent_run_get(run_id: str) -> str:
    """One agent run with its steps, outputs, approvals and metrics."""
    r = agents.get_run(run_id)
    if not r:
        return dump({"error": f"Unknown run: {run_id}"})
    return dump(agents.run_view(r))


@mcp.tool()
def agent_approve(run_id: str, approver: str = "user", execute: bool = True) -> str:
    """Approve a paused agent run (human-in-the-loop gate) and optionally finish executing it."""
    dispatch = _agent_tool_dispatch if execute else None
    return dump(agents.approve_run(run_id, approver=approver, dispatch=dispatch))


@mcp.tool()
def agent_smart_actions(limit: int = 15) -> str:
    """The prioritised "Smart Actions" morning brief across deals, tasks, transactions,
    lease renewals, collections, warm leads and work orders."""
    result = agents.prioritise_actions(_smart_action_signals(), limit=limit)
    return dump(result)


@mcp.tool()
def agent_move_likelihood(lead_id: str) -> str:
    """Score a CRM lead's likelihood of moving (0–100) from lifecycle and engagement signals."""
    lead = next((l for l in leads_db if l.id == lead_id), None)
    if not lead:
        return dump({"error": f"Unknown lead: {lead_id}"})
    return dump({"lead": {"id": lead.id, "name": lead.name, "status": lead.status},
                 "move_likelihood": agents.move_likelihood(_lead_features(lead))})


@mcp.tool()
def agent_seller_intent(equity_pct: float = 0.0, holding_years: float = 0.0,
                        market_heat: float = 0.5, life_event: Optional[str] = None,
                        fsbo_signal: bool = False, engagement_score: int = 40) -> str:
    """Score how likely a contact is to sell (0–100) and recommend the next action."""
    return dump(agents.seller_intent_score({
        "equity_pct": equity_pct, "holding_years": holding_years, "market_heat": market_heat,
        "life_event": life_event, "fsbo_signal": fsbo_signal, "engagement_score": engagement_score}))


@mcp.tool()
def agent_orchestrate(objective: str, agents_csv: str) -> str:
    """Plan a multi-agent hand-off chain for a shared objective (comma-separated agent keys)."""
    keys = [k.strip() for k in (agents_csv or "").split(",") if k.strip()]
    return dump(agents.orchestrate(objective, keys))


@mcp.tool()
def transaction_stages() -> str:
    """The transaction lifecycle stages (draft → … → closed / fallen through)."""
    return dump({"stages": transactions.transaction_stages(),
                 "types": transactions.TRANSACTION_TYPES,
                 "config": transactions.TRANSACTION_CONFIG})


@mcp.tool()
def transaction_create(transaction_type: str = "sale", price: float = 0.0,
                       property_id: Optional[str] = None, property_title: Optional[str] = None,
                       buyer_name: Optional[str] = None, seller_name: Optional[str] = None,
                       listing_agent_id: Optional[str] = None, selling_agent_id: Optional[str] = None,
                       commission_rate: Optional[float] = None, start_date: Optional[str] = None,
                       notes: Optional[str] = None) -> str:
    """Open a transaction with its milestone/deadline checklist (offers, KYC, title,
    financing, signing, NOC, closing, ledger posting, handover)."""
    title = property_title
    if property_id:
        p = find_property(property_id)
        if not p:
            return dump({"error": f"Unknown property: {property_id}"})
        title = title or p.title
    tx = transactions.create_transaction(
        transaction_type=transaction_type, price=price, property_ref=property_id,
        property_title=title, buyer_name=buyer_name, seller_name=seller_name,
        listing_agent_id=listing_agent_id, selling_agent_id=selling_agent_id,
        commission_rate=commission_rate, start_date=start_date, notes=notes, source="mcp")
    return dump({"transaction": transactions.txn_view(tx)})


@mcp.tool()
def transactions_list(status: Optional[str] = None, stage: Optional[str] = None,
                      transaction_type: Optional[str] = None) -> str:
    """List transactions, optionally filtered by status, stage or type."""
    rows = transactions.list_transactions(status=status, stage=stage, transaction_type=transaction_type)
    return dump({"count": len(rows), "transactions": [transactions.txn_view(t) for t in rows]})


@mcp.tool()
def transaction_get(tx_id: str) -> str:
    """One transaction (id or code) with milestones, terms and offers."""
    tx = transactions.get_transaction(tx_id)
    if not tx:
        return dump({"error": f"Unknown transaction: {tx_id}"})
    view = transactions.txn_view(tx)
    view["offers"] = [o.model_dump() for o in transactions.offers_db if o.transaction_id == tx.id]
    view["signatures"] = [s.model_dump() for s in transactions.signatures_db if s.transaction_id == tx.id]
    return dump(view)


@mcp.tool()
def transaction_update(tx_id: str, stage: Optional[str] = None, status: Optional[str] = None,
                       price: Optional[float] = None, commission_rate: Optional[float] = None,
                       buyer_name: Optional[str] = None, seller_name: Optional[str] = None,
                       notes: Optional[str] = None) -> str:
    """Update a transaction's stage, price, parties or commission rate."""
    return dump(transactions.update_transaction(
        tx_id, stage=stage, status=status, price=price, commission_rate=commission_rate,
        buyer_name=buyer_name, seller_name=seller_name, notes=notes))


@mcp.tool()
def transaction_milestone_add(tx_id: str, key: str, name: str, due_date: Optional[str] = None,
                              owner: str = "broker", blocking: bool = False) -> str:
    """Add a custom milestone/deadline to a transaction."""
    return dump(transactions.add_milestone(tx_id, key, name, due_date=due_date, owner=owner,
                                           blocking=blocking))


@mcp.tool()
def transaction_milestone_complete(tx_id: str, key: str, as_of: Optional[str] = None) -> str:
    """Mark a transaction milestone complete."""
    return dump(transactions.complete_milestone(tx_id, key, as_of=as_of))


@mcp.tool()
def transaction_extract_terms(text: str) -> str:
    """Extract key contract terms, parties and dates from a sale/lease agreement text.

    Pulls price, deposit, commission, possession/completion dates, payment terms,
    penalty and tenure with a confidence score — the Transaction Agent's first pass.
    """
    return dump(transactions.extract_terms(text))


@mcp.tool()
def transaction_offer_add(tx_id: str, price: float, buyer_name: Optional[str] = None,
                          terms: Optional[str] = None) -> str:
    """Record an offer on a transaction."""
    return dump(transactions.add_offer(tx_id, price, buyer_name=buyer_name, terms=terms))


@mcp.tool()
def transaction_offer_respond(offer_id: str, action: str, counter_price: Optional[float] = None) -> str:
    """Respond to an offer: ``counter`` (with a price), ``accept``, ``reject`` or ``withdraw``."""
    return dump(transactions.respond_offer(offer_id, action, counter_price=counter_price))


@mcp.tool()
def transaction_signature_add(tx_id: str, signer: str, role: str = "buyer",
                              method: str = "esign", signed: bool = False) -> str:
    """Record an e-signature request / signing for a transaction party."""
    return dump(transactions.add_signature(tx_id, signer, role=role, method=method, signed=signed))


@mcp.tool()
def transaction_signatures(tx_id: str) -> str:
    """E-signature status: signed roles, missing roles and completeness."""
    return dump(transactions.verify_signatures(tx_id))


@mcp.tool()
def transaction_progress(tx_id: str) -> str:
    """Completion %, overdue milestones, next deadline and a red/amber/green status."""
    return dump(transactions.transaction_progress(tx_id))


@mcp.tool()
def transaction_deadlines(horizon_days: int = 14) -> str:
    """Every transaction milestone due within the horizon (incl. overdue), soonest first."""
    return dump(transactions.upcoming_deadlines(horizon_days))


@mcp.tool()
def transaction_close(tx_id: str, commission_rate: Optional[float] = None,
                      platform_share: float = 0.20, listing_agent_share: float = 0.40,
                      selling_agent_share: float = 0.40, post_to_ledger: bool = True,
                      record_payouts: bool = True) -> str:
    """Close a transaction: compute commission + VAT, allocate the revenue share, post the
    balanced journal entry to the ledger and record the agent/platform payouts."""
    result = transactions.close_transaction(
        tx_id, commission_rate=commission_rate,
        splits={"platform_share": platform_share, "listing_agent_share": listing_agent_share,
                "selling_agent_share": selling_agent_share})
    if "error" in result:
        return dump(result)
    tx = transactions.get_transaction(tx_id)
    if post_to_ledger:
        entry = accounting.post_journal_entry(
            result["ledger_lines"], memo=f"Commission on {tx.code}", reference=tx.code,
            source="transaction", source_id=tx.id)
        result["journal_entry"] = {"id": entry.get("id"), "entry_no": entry.get("entry_no")} \
            if "error" not in entry else entry
    if record_payouts and tx:
        payouts = []
        splits = result["revenue_share"]["splits"]
        gross = result["commission"]["gross"]
        platform = splits.get("platform_share", 0.20)
        payouts.append(commercial.record_payout(tx.id, gross, "platform", platform,
                                                role="platform").model_dump())
        listing_share = splits.get("listing_agent_share", 0.40)
        selling_share = splits.get("selling_agent_share", 0.40)
        for agent_id, share in ((tx.listing_agent_id, listing_share),
                                (tx.selling_agent_id, selling_share)):
            if agent_id:
                payouts.append(commercial.record_payout(tx.id, gross, agent_id, share,
                                                        role="agent").model_dump())
        result["payouts"] = payouts
        result["revenue_allocation"] = result["revenue_share"]["allocation"]
    return dump(result)


@mcp.tool()
def transaction_report(tx_id: str, lang: str = "en", theme: str = "auto") -> str:
    """Render a printable HTML transaction/closing report (HTML)."""
    tx = transactions.get_transaction(tx_id)
    if not tx:
        return dump({"error": f"Unknown transaction: {tx_id}"})
    prog = transactions.transaction_progress(tx.id)
    offers = [o for o in transactions.offers_db if o.transaction_id == tx.id]
    sigs = transactions.verify_signatures(tx.id)
    rate = tx.commission_rate or transactions.TRANSACTION_CONFIG["default_commission_rate"]
    gross = round(tx.price * rate, 2)
    sections: List[Dict[str, Any]] = [
        {"kind": "cards", "heading": "Transaction summary", "items": [
            ["Code", tx.code, transactions.TRANSACTION_TYPES.get(tx.transaction_type, tx.transaction_type)],
            ["Status", tx.status, tx.stage],
            ["Price", f"PKR {tx.price:,.0f}", "sale price"],
            ["Progress", f"{prog['progress_pct']}%", f"{prog['milestones_done']}/{prog['milestones_total']} milestones"],
            ["RAG", prog["rag"], "deadline health"]]},
        {"kind": "kv", "heading": "Parties & commission", "items": [
            ["Buyer", tx.buyer_name or "—"], ["Seller", tx.seller_name or "—"],
            ["Listing agent", tx.listing_agent_id or "—"], ["Selling agent", tx.selling_agent_id or "—"],
            ["Commission rate", f"{rate * 100:.2f}%"], ["Gross commission", f"PKR {gross:,.0f}"],
            ["VAT", f"PKR {round(gross * transactions.TRANSACTION_CONFIG['vat_rate'], 2):,.0f}"],
            ["Signatures", f"{len(sigs['signed_roles'])}/{len(sigs['expected_roles'])} complete"]]},
        {"kind": "table", "heading": "Milestones & deadlines",
         "columns": ["Milestone", "Owner", "Due", "Status", "Blocking"],
         "rows": [[m.name, m.owner, m.due_date or "—", m.status, "yes" if m.blocking else "no"]
                  for m in tx.milestones]},
        {"kind": "table", "heading": "Offers",
         "columns": ["Price", "Buyer", "Status", "Counter", "Date"],
         "numeric": ["Price", "Counter"],
         "rows": [[f"PKR {o.price:,.0f}", o.buyer_name or "—", o.status,
                   (f"PKR {o.counter_price:,.0f}" if o.counter_price else "—"), o.created_at]
                  for o in offers]},
    ]
    ads = content.ad_section(slot="infeed", category="construction_technique", lang=lang)
    if ads.get("count"):
        sections.append(ads)
    return gis.build_report_html(title=f"Transaction {tx.code}",
                                 subtitle=f"{tx.property_title or ''} · {tx.stage}",
                                 sections=sections, ticker_html=_portal_ticker(lang),
                                 lang=lang, theme=theme)


@mcp.tool()
def buyer_parse_requirement(text: str) -> str:
    """Parse a natural-language buyer brief into a structured requirement.

    Understands budget ranges (``800k``, ``3 crore``, ``1.2 million``), commute caps
    ("35 minutes"), bedrooms, city, property type, family size, timeline and
    must-have/nice-to-have features — bilingual English keywords.
    """
    return dump(intelligence.parse_requirement(text, known_cities=[c.name for c in cities_db]))


@mcp.tool()
def buyer_recommend(text: Optional[str] = None, limit: int = 8, city: Optional[str] = None,
                    category: Optional[str] = None, use_type: Optional[str] = None,
                    max_price: Optional[float] = None) -> str:
    """Conversational buyer agent: parse the brief, then rank live listings on weighted
    GIS/accounting dimensions (price fit, commute, schools, safety, amenities,
    liquidity, condition, size) with reasons, flags and bands."""
    return dump(_buyer_recommend_impl(text=text, limit=limit, city=city, category=category,
                                      use_type=use_type, max_price=max_price))


@mcp.tool()
def buyer_anomaly_scan(city: Optional[str] = None, category: Optional[str] = None,
                       use_type: Optional[str] = None, threshold: float = 1.0) -> str:
    """Z-score the market: surface listings priced below their area average (bargains)
    and above it (overpriced), grouped by city."""
    rows = list(properties_db)
    if city:
        c = resolve_city(city)
        if c:
            rows = [p for p in rows if p.city_id == c.id]
    if category:
        rows = [p for p in rows if p.category == category]
    if use_type:
        rows = [p for p in rows if p.use_type == use_type]
    return dump(intelligence.anomaly_scan([_property_candidate(p) for p in rows],
                                          threshold=threshold))


@mcp.tool()
def buyer_affordability(price: float, down_payment_share: float = 0.25,
                        annual_rate: Optional[float] = None, years: Optional[int] = None,
                        monthly_income: Optional[float] = None, property_tax_rate: float = 0.01,
                        holding_monthly: float = 0.0, other_debt_monthly: float = 0.0) -> str:
    """Monthly payment, property tax, holding costs and a debt-to-income verdict for a price."""
    return dump(intelligence.affordability(
        price, down_payment_share=down_payment_share, annual_rate=annual_rate, years=years,
        monthly_income=monthly_income, property_tax_rate=property_tax_rate,
        holding_monthly=holding_monthly, other_debt_monthly=other_debt_monthly))


@mcp.tool()
def seller_cma(property_id: str, comp_ids: Optional[List[str]] = None) -> str:
    """Seller pricing agent: adjusted comparable-market analysis for a property.

    Adjusts comparables for area, age, condition and location, then returns a
    low/target/high price range, a confidence score, expected days-on-market and a
    pricing strategy.
    """
    return dump(_seller_cma_impl(property_id, comp_ids))


@mcp.tool()
def seller_net_proceeds(price: float, commission_rate: float = 0.02, other_cost_rate: float = 0.01,
                        mortgage_payoff: float = 0.0, cost_basis: Optional[float] = None,
                        capital_gains_rate: Optional[float] = None) -> str:
    """A seller's net cash after commission, selling costs, mortgage payoff and capital gains."""
    return dump(intelligence.net_proceeds(
        price, commission_rate=commission_rate, other_cost_rate=other_cost_rate,
        mortgage_payoff=mortgage_payoff, cost_basis=cost_basis,
        capital_gains_rate=capital_gains_rate))


@mcp.tool()
def seller_marketing_assets(property_id: str, tone: str = "professional",
                            lang: str = "en") -> str:
    """Generate a full marketing kit for a listing: headline, description, bullets,
    social posts, e-mail, drone/video script, staging suggestions, keywords and hashtags."""
    p = find_property(property_id)
    if not p:
        return dump({"error": f"Unknown property: {property_id}"})
    listing = {"id": p.id, "title": p.title, "city": city_name(p.city_id),
               "scheme": _scheme_label(p.scheme_id), "price": p.price, "covered_area": p.covered_area,
               "plot_area": p.plot_area, "bedrooms": p.bedrooms, "category": p.category,
               "features": [f for f in (p.landmark, p.sector) if f]}
    return dump(intelligence.generate_listing_assets(listing, lang=lang, tone=tone))


@mcp.tool()
def investment_underwrite(purchase_price: float, monthly_rent: float = 0.0,
                          annual_rent: Optional[float] = None, down_payment_share: float = 0.25,
                          loan_rate: Optional[float] = None, loan_years: int = 20,
                          vacancy_rate: float = 0.05, operating_expense_rate: float = 0.30,
                          appreciation_rate: float = 0.06, exit_cap_rate: float = 0.07,
                          hold_years: int = 10, tax_rate: float = 0.0) -> str:
    """Underwrite a deal: NOI, debt service, DSCR, cap rate, cash-on-cash, after-tax cash
    flow, IRR/NPV/equity multiple, an exit valuation and a risk-adjusted grade."""
    return dump(intelligence.underwrite({
        "purchase_price": purchase_price, "monthly_rent": monthly_rent, "annual_rent": annual_rent,
        "down_payment_share": down_payment_share, "loan_rate": loan_rate, "loan_years": loan_years,
        "vacancy_rate": vacancy_rate, "operating_expense_rate": operating_expense_rate,
        "appreciation_rate": appreciation_rate, "exit_cap_rate": exit_cap_rate,
        "hold_years": hold_years, "tax_rate": tax_rate}))


@mcp.tool()
def investment_screen(city: Optional[str] = None, category: Optional[str] = None,
                      rental_yield: float = 0.045, min_cap_rate: Optional[float] = None,
                      min_dscr: Optional[float] = None, max_price: Optional[float] = None,
                      down_payment_share: float = 0.25, loan_rate: float = 0.16,
                      loan_years: int = 20, hold_years: int = 10, limit: int = 10) -> str:
    """Agentic Investment Screener: underwrite the live listing book against criteria and
    return a risk-adjusted shortlist, plus the rejected sample and a pass rate."""
    crit = {"city": city, "category": category, "rental_yield": rental_yield,
            "min_cap_rate": min_cap_rate, "min_dscr": min_dscr, "max_price": max_price,
            "down_payment_share": down_payment_share, "loan_rate": loan_rate,
            "loan_years": loan_years, "hold_years": hold_years}
    result = _screen_over_properties(crit)
    result["top_picks"] = result["top_picks"][:limit]
    return dump(result)


@mcp.tool()
def investment_portfolio_alerts(holdings: Optional[List[Dict[str, Any]]] = None,
                                interest_rate: float = 0.18, rent_index_change: float = 0.0,
                                supply_change: float = 0.0, market_heat: float = 0.5) -> str:
    """Proactive investor alerts: exit windows closing, refinance opportunities and
    market-risk warnings for a portfolio. Omit ``holdings`` to derive them from the
    listing book."""
    if not holdings:
        holdings = [{"id": p.id, "title": p.title, "purchase_value": p.price,
                     "current_value": round((p.price or 0.0) * 1.25, 2), "hold_years": 6,
                     "target_hold_years": 7, "loan_balance": round((p.price or 0.0) * 0.5, 2)}
                    for p in properties_db[:10]]
    return dump(intelligence.portfolio_alerts(holdings, {
        "interest_rate": interest_rate, "rent_index_change": rent_index_change,
        "supply_change": supply_change, "market_heat": market_heat}))


@mcp.tool()
def buyer_report(text: str, lang: str = "en", theme: str = "auto") -> str:
    """Render the conversational buyer agent's brief, shortlist and bargain scan as HTML."""
    ranked = _buyer_recommend_impl(text=text, limit=8)
    parsed = ranked.get("requirement", {})
    shortlist = ranked.get("shortlist", [])
    req_cards = [[k.replace("_", " ").title(), str(v), "parsed"] for k, v in parsed.items()
                 if not isinstance(v, list)][:8]
    sections: List[Dict[str, Any]] = [
        {"kind": "text", "heading": "Your brief", "text": text},
        {"kind": "cards", "heading": "Parsed requirement", "items": req_cards or
         [["Note", "no structured fields found", "add budget/commute/type"]]},
        {"kind": "table", "heading": "Ranked shortlist",
         "columns": ["Rank", "Property", "Price", "Composite", "Band", "Reasons"],
         "numeric": ["Rank", "Price", "Composite"],
         "rows": [[s["rank"], s["title"], s["price"], s["composite"], s["band"],
                   "; ".join(s["reasons"])] for s in shortlist]},
    ]
    if parsed.get("must_have"):
        sections.append({"kind": "pills", "heading": "Must-have features",
                         "items": list(parsed["must_have"])})
    ads = content.ad_section(slot="banner", category="smart_technology", lang=lang)
    if ads.get("count"):
        sections.append(ads)
    return gis.build_report_html(title="Buyer brief & shortlist",
                                 subtitle=parsed.get("city", "") or "conversational buyer agent",
                                 sections=sections, ticker_html=_portal_ticker(lang),
                                 lang=lang, theme=theme)


@mcp.tool()
def seller_report(property_id: str, lang: str = "en", theme: str = "auto") -> str:
    """Render a seller CMA + net-proceeds + marketing HTML report."""
    p = find_property(property_id)
    if not p:
        return dump({"error": f"Unknown property: {property_id}"})
    cma = _seller_cma_impl(property_id)
    if "error" in cma:
        return dump(cma)
    range_ = cma["price_range"]
    proceeds = intelligence.net_proceeds(range_["target"])
    assets = intelligence.generate_listing_assets({
        "title": p.title, "city": city_name(p.city_id), "scheme": _scheme_label(p.scheme_id),
        "price": range_["target"], "covered_area": p.covered_area, "bedrooms": p.bedrooms})
    sections: List[Dict[str, Any]] = [
        {"kind": "cards", "heading": "Recommended pricing", "items": [
            ["Low", f"PKR {range_['low']:,.0f}", "25th percentile"],
            ["Target", f"PKR {range_['target']:,.0f}", "list here"],
            ["High", f"PKR {range_['high']:,.0f}", "75th percentile"],
            ["Confidence", f"{int(cma['confidence'] * 100)}%", f"{cma['comp_count']} comps"],
            ["Expected DOM", f"{int(cma['expected_days_on_market'])} days", "at target"]]},
        {"kind": "table", "heading": "Adjusted comparables",
         "columns": ["Comp", "Raw price", "Area", "Adjust factor", "Adjusted price"],
         "numeric": ["Raw price", "Area", "Adjust factor", "Adjusted price"],
         "rows": [[a["title"], a["raw_price"], a["area"], a["adjust_factor"], a["adjusted_price"]]
                  for a in cma["adjusted_comps"]]},
        {"kind": "kv", "heading": "Seller net proceeds (at target)",
         "items": [[k.replace("_", " ").title(), f"{v:,.0f}" if isinstance(v, (int, float)) else str(v)]
                   for k, v in proceeds.items()]},
        {"kind": "text", "heading": "Listing copy", "text": assets["description"]},
        {"kind": "pills", "heading": "Staging suggestions", "items": assets["staging_suggestions"]},
    ]
    ads = content.ad_section(slot="infeed", category="materials", lang=lang)
    if ads.get("count"):
        sections.append(ads)
    return gis.build_report_html(title="Seller pricing & marketing report",
                                 subtitle=p.title, sections=sections,
                                 ticker_html=_portal_ticker(lang), lang=lang, theme=theme)


@mcp.tool()
def investment_report(city: Optional[str] = None, rental_yield: float = 0.045,
                      min_cap_rate: float = 0.025, lang: str = "en", theme: str = "auto") -> str:
    """Render the investment screener's shortlist, alerts and GTK as an HTML report."""
    screen = _screen_over_properties({"city": city, "rental_yield": rental_yield,
                                      "min_cap_rate": min_cap_rate})
    holdings = [{"id": p.id, "title": p.title, "purchase_value": p.price,
                 "current_value": round((p.price or 0.0) * 1.25, 2), "hold_years": 6,
                 "target_hold_years": 7, "loan_balance": round((p.price or 0.0) * 0.5, 2)}
                for p in properties_db[:8]]
    alerts = intelligence.portfolio_alerts(holdings, {"market_heat": 0.8, "interest_rate": 0.14})
    sections: List[Dict[str, Any]] = [
        {"kind": "cards", "heading": "Screen",
         "items": [["Considered", screen["considered"], "live listings"],
                   ["Passed", screen["passed"], "met the criteria"],
                   ["Pass rate", f"{screen['pass_rate_pct']}%", "vs criteria"],
                   ["Alerts", alerts["count"], "portfolio"]]},
        {"kind": "table", "heading": "Top risk-adjusted picks",
         "columns": ["Rank", "Property", "City", "Cap rate", "DSCR", "IRR", "Score", "Grade"],
         "numeric": ["Rank", "Cap rate", "DSCR", "IRR", "Score"],
         "rows": [[r["rank"], r["title"], r["city"], round(r["cap_rate"] * 100, 2),
                   r["dscr"], round((r["irr"] or 0) * 100, 2), r["score"], r["grade"]]
                  for r in screen["top_picks"]]},
        {"kind": "table", "heading": "Portfolio alerts",
         "columns": ["Type", "Asset", "Severity", "Message"],
         "rows": [[a["type"], a["title"], a["severity"], a["message"]] for a in alerts["alerts"]]},
    ]
    ads = content.ad_section(slot="banner", category="smart_technology", lang=lang)
    if ads.get("count"):
        sections.append(ads)
    return gis.build_report_html(title="Investment screener report",
                                 subtitle=city or "whole portfolio", sections=sections,
                                 ticker_html=_portal_ticker(lang), lang=lang, theme=theme)


@mcp.tool()
def leasing_units(status: Optional[str] = None, city: Optional[str] = None,
                  limit: int = 50) -> str:
    """Rental units available to the autonomous leasing agent (net of registered units and
    let-able listings), with rent, floor rent and holding cost."""
    rows = list(leasing.units_db)
    if city:
        c = resolve_city(city)
        if c:
            rows = [u for u in rows if (u.city or "").lower() == c.name.lower()]
    if status:
        rows = [u for u in rows if u.status == status]
    return dump({"count": len(rows), "units": [u.model_dump() for u in rows[:limit]]})


@mcp.tool()
def leasing_unit(unit_id: str) -> str:
    """One rental unit by id."""
    u = next((x for x in leasing.units_db if x.id == unit_id), None)
    if not u:
        return dump({"error": f"Unknown unit: {unit_id}"})
    return dump(u.model_dump())


@mcp.tool()
def leasing_unit_create(title: str, rent: float = 0.0, city: Optional[str] = None,
                        scheme: Optional[str] = None, bedrooms: Optional[int] = None,
                        area: Optional[float] = None, deposit: float = 0.0,
                        monthly_holding_cost: float = 0.0,
                        amenities: Optional[List[str]] = None) -> str:
    """Register a rental unit (with monthly holding cost so a rent floor can be enforced)."""
    unit = leasing.RentalUnit(title=title, rent=rent, city=city, scheme=scheme, bedrooms=bedrooms,
                              area=area, deposit=deposit, monthly_holding_cost=monthly_holding_cost,
                              amenities=amenities or [])
    unit.floor_rent = leasing.rent_floor(monthly_holding_cost)["rent_floor"]
    leasing.units_db.append(unit)
    return dump({"unit": unit.model_dump()})


@mcp.tool()
def leasing_rent_floor(monthly_holding_cost: float, margin: Optional[float] = None) -> str:
    """The minimum rent that keeps a unit cash-flow positive (holding cost + margin)."""
    return dump(leasing.rent_floor(monthly_holding_cost, margin))


@mcp.tool()
def leasing_inquiry(message: str, unit_id: Optional[str] = None, channel: str = "web_chat",
                    lang: str = "en") -> str:
    """Autonomous leasing agent: classify a tenant inquiry, draft a reply and decide whether
    it is auto-handled — across web chat, WhatsApp, SMS, e-mail and voice."""
    unit = next((u for u in leasing.units_db if u.id == unit_id), None)
    if unit_id and not unit:
        return dump({"error": f"Unknown unit: {unit_id}"})
    if unit is None and leasing.units_db:
        unit = leasing.units_db[0]
    return dump(leasing.handle_inquiry(unit, message, channel=channel, lang=lang).model_dump())


@mcp.tool()
def leasing_inquiries(unit_id: Optional[str] = None, intent: Optional[str] = None) -> str:
    """Log of handled leasing inquiries (optionally filtered by unit or intent)."""
    rows = list(leasing.inquiries_db)
    if unit_id:
        rows = [i for i in rows if i.unit_id == unit_id]
    if intent:
        rows = [i for i in rows if i.intent == intent]
    return dump({"count": len(rows), "inquiries": [i.model_dump() for i in rows]})


@mcp.tool()
def leasing_screen_application(applicant: str, monthly_income: float,
                               unit_id: Optional[str] = None, employment: str = "salaried",
                               references_count: int = 0, credit_proxy: int = 70,
                               occupants: int = 1, pets: bool = False,
                               move_in_days: int = 15) -> str:
    """Screen a rental application: income-to-rent, references, credit proxy and employment
    → approve / conditional / decline with conditions and a recommended deposit."""
    unit = next((u for u in leasing.units_db if u.id == unit_id), None)
    app = leasing.Application(unit_id=unit_id, applicant=applicant, monthly_income=monthly_income,
                              employment=employment, references_count=references_count,
                              credit_proxy=credit_proxy, occupants=occupants, pets=pets,
                              move_in_days=move_in_days)
    leasing.applications_db.append(app)
    return dump(leasing.screen_application(app, unit))


@mcp.tool()
def leasing_renewals(uplift: float = 0.08, hold_rent_if_risky: bool = True) -> str:
    """Renewal Agent: recommend renewal rents and retention actions for every active lease."""
    rows = []
    today = datetime.now().date()
    for lease in accounting.leases_db:
        if lease.status != "active":
            continue
        days = (lease.end_date - today).days if lease.end_date else 365
        rows.append(leasing.renewal_recommendation(
            {"rent_amount": lease.rent_amount, "days_to_expiry": days, "lease_id": lease.id},
            {"market_rent": round(lease.rent_amount * (1 + uplift), 2)},
            {"on_time_payment_rate": 0.96}))
    return dump({"count": len(rows), "uplift": uplift, "renewals": rows})


@mcp.tool()
def leasing_collection() -> str:
    """Rent-collection board: active leases, arrears and total outstanding from the ledger."""
    leases = [{"id": l.id, "tenant": l.tenant, "unit_label": l.unit_label}
              for l in accounting.leases_db if l.status == "active"]
    invoices = [{"lease_id": inv.lease_id, "balance": inv.balance}
                for inv in accounting.invoices_db if inv.lease_id]
    return dump(leasing.rent_collection_status(leases, invoices))


@mcp.tool()
def leasing_funnel() -> str:
    """Leasing funnel: inquiries, auto-handled share, applications and channel/intent mix."""
    return dump(leasing.leasing_funnel())


@mcp.tool()
def leasing_portal(lang: str = "en", theme: str = "auto") -> str:
    """Render the **Autonomous Leasing wing** portal page (HTML) with a live rent-floor and
    screening calculator."""
    units = leasing.units_db
    funnel = leasing.leasing_funnel()
    unit_rows = [[u.title, u.city or "—", f"PKR {u.rent:,.0f}",
                  f"PKR {(u.floor_rent or 0):,.0f}", u.status] for u in units]
    channel_rows = [[c, n] for c, n in funnel["by_channel"].items()]
    sections: List[Dict[str, Any]] = [
        {"kind": "cards", "heading": "Leasing at a glance", "items": [
            ["Units", len(units), "registered"],
            ["Inquiries", funnel["inquiries"], "handled"],
            ["Auto-handled", funnel["auto_handled"], "no human touch"],
            ["Escalated", funnel["escalated"], "needs a human"],
            ["Applications", funnel["applications"], "screened"],
            ["Channels", len(leasing.LEASING_CONFIG["channels"]), "web → voice"]]},
        {"kind": "text", "heading": "About this wing", "text": (
            "The autonomous leasing agent holds 24/7 conversations across web chat, WhatsApp, "
            "SMS, e-mail and voice, answers availability/price/amenity/commute/schools questions, "
            "pre-screens applicants and recommends renewals — never letting a unit below its "
            "holding-cost floor. Screening and collection read the same ledger as accounting.")},
        {"kind": "table", "heading": "Rental units",
         "columns": ["Unit", "City", "Rent", "Floor rent", "Status"], "rows": unit_rows},
        {"kind": "table", "heading": "Inquiry channels",
         "columns": ["Channel", "Inquiries"], "numeric": ["Inquiries"], "rows": channel_rows},
        {"kind": "html", "heading": "Rent floor & screening calculator",
         "html": _leasing_calculator_html()},
    ]
    ads = content.ad_section(slot="infeed", category="smart_technology", lang=lang)
    if ads.get("count"):
        sections.append(ads)
    return gis.build_report_html(title="Autonomous Leasing wing",
                                 subtitle="24/7 inquiry handling · screening · renewals · rent floor",
                                 sections=sections, ticker_html=_portal_ticker(lang),
                                 lang=lang, theme=theme)


def _leasing_calculator_html() -> str:
    payload = {"margin": leasing.LEASING_CONFIG["default_rent_floor_margin"],
               "min_itr": leasing.LEASING_CONFIG["screening"]["min_income_to_rent"]}
    sel = ("padding:6px;border:1px solid var(--line);background:var(--surface);color:var(--ink);"
           "border-radius:6px")
    return (
        '<div style="display:flex;flex-wrap:wrap;gap:12px;align-items:flex-end">'
        f'<label>Monthly holding cost (PKR)<br><input id="lc-cost" type="number" value="70000" min="0" style="{sel};width:180px"></label>'
        f'<label>Proposed rent (PKR)<br><input id="lc-rent" type="number" value="90000" min="0" style="{sel};width:160px"></label>'
        f'<label>Applicant income (PKR)<br><input id="lc-inc" type="number" value="280000" min="0" style="{sel};width:180px"></label>'
        '</div>'
        '<h3 id="lc-out" style="margin:16px 0 4px">…</h3>'
        '<div id="lc-detail" style="color:var(--muted);font-size:13px"></div>'
        '<script>(function(){var D=' + json.dumps(payload) + ';'
        'function calc(){var cost=+document.getElementById("lc-cost").value||0,'
        'rent=+document.getElementById("lc-rent").value||0,inc=+document.getElementById("lc-inc").value||0;'
        'var floor=cost*(1+D.margin);var itr=rent>0?inc/rent:0;'
        'var ok=rent>=floor;var dec=itr>=D.min_itr?"approve":(itr>=D.min_itr*0.66?"conditional":"decline");'
        'document.getElementById("lc-out").textContent="Rent floor Rs "+Math.round(floor).toLocaleString()'
        '+" · "+(ok?"VIABLE":"BELOW FLOOR")+" · screening: "+dec;'
        'document.getElementById("lc-detail").textContent="Income-to-rent "+itr.toFixed(2)+"x (min "+D.min_itr+"x)"'
        '+(ok?"":(" · shortfall Rs "+Math.round(floor-rent).toLocaleString()));}'
        '["lc-cost","lc-rent","lc-inc"].forEach(function(id){document.getElementById(id).addEventListener("input",calc);});'
        'calc();})();</script>'
    )


def _marketing_lead_from(lead: Lead) -> marketing.MarketingLead:
    interactions = [i for i in interactions_db if i.entity_type == "lead" and i.entity_id == lead.id]
    last = max((i.occurred_at for i in interactions), default=lead.updated_at)
    days = max(0, (datetime.now() - last).days)
    return marketing.MarketingLead(
        name=lead.name, channel=lead.source, language="en", budget_min=lead.budget_min,
        budget_max=lead.budget_max, city=city_name(lead.city_id) if lead.city_id else None,
        use_type=lead.interest_use_type, interest_category=lead.interest_category,
        engagement=lead.score or 40, stage=lead.status if lead.status in marketing.LEAD_STAGES else "new",
        last_contact_days=days, assigned_agent_id=lead.assigned_agent_id)


@mcp.tool()
def marketing_channels() -> str:
    """Cross-channel lead sources and their qualification quality, plus the content kinds."""
    return dump({"channels": marketing.MARKETING_CONFIG["channel_quality"],
                 "lead_stages": marketing.LEAD_STAGES,
                 "content_kinds": marketing.MARKETING_CONFIG["content_kinds"]})


@mcp.tool()
def marketing_routes() -> str:
    """Lead-routing rules (postcode/city/language/price/source → agent, queue and SLA)."""
    return dump({"count": len(marketing.routes_db),
                 "routes": [r.model_dump() for r in marketing.routes_db]})


@mcp.tool()
def marketing_route_add(name: str, match: Dict[str, Any],
                        assign_to_agent_id: Optional[str] = None, queue: str = "general",
                        priority: int = 100, sla_hours: int = 4) -> str:
    """Add a lead-routing rule. ``match`` may carry city, language, source, use_type,
    price_min, price_max or postcode_prefix."""
    rule = marketing.add_route(name, match, assign_to_agent_id=assign_to_agent_id, queue=queue,
                               priority=priority, sla_hours=sla_hours)
    return dump({"route": rule.model_dump()})


@mcp.tool()
def marketing_qualify(lead_id: str) -> str:
    """Qualify a CRM lead: score (0–100), band, reasons and recommended action; syncs the
    score back onto the lead."""
    lead = next((l for l in leads_db if l.id == lead_id), None)
    if not lead:
        return dump({"error": f"Unknown lead: {lead_id}"})
    ml = _marketing_lead_from(lead)
    result = marketing.qualify_lead(ml)
    lead.score = result["score"]
    lead.updated_at = datetime.now()
    return dump({"lead": {"id": lead.id, "name": lead.name}, "qualification": result})


@mcp.tool()
def marketing_route_lead(lead_id: str) -> str:
    """Route a CRM lead to the best-matching rule, queue, agent and SLA."""
    lead = next((l for l in leads_db if l.id == lead_id), None)
    if not lead:
        return dump({"error": f"Unknown lead: {lead_id}"})
    ml = _marketing_lead_from(lead)
    marketing.qualify_lead(ml)
    route = marketing.route_lead(ml)
    if route.get("assigned_agent_id"):
        lead.assigned_agent_id = route["assigned_agent_id"]
    return dump({"lead": {"id": lead.id, "name": lead.name, "band": ml.band}, "routing": route})


@mcp.tool()
def marketing_reengagement(inactive_days: Optional[int] = None,
                           min_score: Optional[int] = None) -> str:
    """Re-engagement Agent: mine dormant and previously-lost leads, flag false negatives and
    draft reactivation outreach."""
    leads = [_marketing_lead_from(l) for l in leads_db]
    return dump(marketing.reengagement_candidates(leads, inactive_days=inactive_days,
                                                  min_score=min_score))


@mcp.tool()
def marketing_generate_content(kind: str = "market_report", property_id: Optional[str] = None,
                               tone: str = "professional", lang: str = "en",
                               topic: Optional[str] = None) -> str:
    """Generate a marketing content asset (listing description, social post, reel script,
    e-mail, market report or video script). Human approval required before publishing."""
    listing: Dict[str, Any] = {}
    if property_id:
        p = find_property(property_id)
        if not p:
            return dump({"error": f"Unknown property: {property_id}"})
        listing = {"id": p.id, "title": p.title, "city": city_name(p.city_id),
                   "scheme": _scheme_label(p.scheme_id), "price": p.price,
                   "covered_area": p.covered_area, "bedrooms": p.bedrooms, "category": p.category}
    asset = marketing.generate_content(kind, listing=listing, ref=property_id, tone=tone,
                                       lang=lang, topic=topic)
    return dump({"asset": asset.model_dump()})


@mcp.tool()
def marketing_content_assets(status: Optional[str] = None) -> str:
    """Content assets awaiting approval, approved or published."""
    rows = marketing.assets_db
    if status:
        rows = [a for a in rows if a.status == status]
    return dump({"count": len(rows), "assets": [a.model_dump() for a in rows]})


@mcp.tool()
def marketing_content_approve(asset_id: str, approver: str = "user") -> str:
    """Human approval gate for a generated content asset."""
    return dump(marketing.approve_content(asset_id, approver=approver))


@mcp.tool()
def marketing_campaign_plan(objective: str, budget: float, channels: List[str],
                            days: int = 14, audience: Optional[int] = None) -> str:
    """Plan a multichannel campaign: budget allocation, a day-by-day schedule and KPIs."""
    cmp = marketing.campaign_plan(objective, budget, channels, days=days, audience=audience)
    return dump({"campaign": cmp.model_dump()})


@mcp.tool()
def marketing_funnel() -> str:
    """Lead funnel: counts by stage, band and channel with conversion metrics."""
    return dump(marketing.funnel_stats([_marketing_lead_from(l) for l in leads_db]))


@mcp.tool()
def marketing_portal(lang: str = "en", theme: str = "auto") -> str:
    """Render the **AI Marketing Conductor wing** portal page (HTML) with routing, funnel and
    re-engagement views."""
    leads = [_marketing_lead_from(l) for l in leads_db]
    for ml in leads:
        marketing.qualify_lead(ml)
    funnel = marketing.funnel_stats(leads)
    re_ = marketing.reengagement_candidates(leads)
    route_rows = [[r.name, json.dumps(r.match), r.queue, r.assign_to_agent_id or "—", r.sla_hours]
                  for r in marketing.routes_db]
    band_rows = [[b, n] for b, n in funnel["by_band"].items()]
    sections: List[Dict[str, Any]] = [
        {"kind": "cards", "heading": "Marketing at a glance", "items": [
            ["Leads", funnel["leads"], "cross-channel"],
            ["Hot", funnel["by_band"].get("hot", 0), "call now"],
            ["Qualified", funnel["qualified"], "in progress"],
            ["Won", funnel["won"], f"{funnel['conversion_pct']}% conversion"],
            ["Routes", len(marketing.routes_db), "routing rules"],
            ["Re-engage", re_["candidates"], "dormant / false negatives"]]},
        {"kind": "text", "heading": "About this wing", "text": (
            "The AI Marketing Conductor captures leads across every channel, qualifies and "
            "routes them by postcode, language and budget, revives dormant leads the system had "
            "written off, generates content and plans campaigns — as a bundleable module on top "
            "of the CRM.")},
        {"kind": "table", "heading": "Routing rules",
         "columns": ["Rule", "Match", "Queue", "Agent", "SLA (h)"], "rows": route_rows},
        {"kind": "table", "heading": "Lead bands",
         "columns": ["Band", "Leads"], "numeric": ["Leads"], "rows": band_rows},
        {"kind": "table", "heading": "Re-engagement candidates",
         "columns": ["Name", "Score", "Stage", "Reason", "Drafted outreach"],
         "rows": [[r["name"], r["score"], r["stage"], r["reason"], r["outreach"]]
                  for r in re_["revived"]]},
    ]
    ads = content.ad_section(slot="infeed", category="smart_technology", lang=lang)
    if ads.get("count"):
        sections.append(ads)
    return gis.build_report_html(title="AI Marketing Conductor wing",
                                 subtitle="Lead engine · routing · re-engagement · content",
                                 sections=sections, ticker_html=_portal_ticker(lang),
                                 lang=lang, theme=theme)


@mcp.tool()
def commercial_products(category: Optional[str] = None, priority: Optional[str] = None) -> str:
    """The commercial product catalogue: the 8 products with segment, pricing models,
    positioning, price-from and priority (P0–P2)."""
    return dump({"count": len(commercial.PRODUCTS),
                 "products": commercial.product_catalog(category=category, priority=priority)})


@mcp.tool()
def commercial_product(key: str) -> str:
    """One commercial product by key (e.g. ``broker_ai_workspace``)."""
    p = commercial.find_product(key)
    if not p:
        return dump({"error": f"Unknown product: {key}",
                     "keys": [x["key"] for x in commercial.PRODUCTS]})
    p = dict(p)
    p["plans"] = commercial.plan_catalog(key)
    return dump(p)


@mcp.tool()
def commercial_plans(product: Optional[str] = None) -> str:
    """Subscription / usage plans (price, interval, included units, overage rate, seats)."""
    rows = commercial.plan_catalog(product)
    return dump({"count": len(rows), "plans": rows})


@mcp.tool()
def commercial_plan(key: str) -> str:
    """One pricing plan by key (e.g. ``mcp_growth``)."""
    plan = commercial.find_plan(key)
    if not plan:
        return dump({"error": f"Unknown plan: {key}", "keys": [p["key"] for p in commercial.PLANS]})
    plan["product_detail"] = commercial.find_product(plan["product"])
    return dump(plan)


@mcp.tool()
def commercial_pricing_matrix() -> str:
    """The hybrid-pricing matrix (subscription + usage + performance + licence) with the GTM playbook."""
    return dump(commercial.pricing_matrix())


@mcp.tool()
def commercial_recommend_package(segment: str, seats: int = 1, expected_calls: int = 0,
                                 product: Optional[str] = None) -> str:
    """Recommend the best-fit plan for a segment/seat-count/usage and estimate the monthly bill."""
    return dump(commercial.recommend_package(segment, seats=seats, expected_calls=expected_calls,
                                             product=product))


@mcp.tool()
def commercial_subscribe(account: str, plan_key: str, seats: int = 1) -> str:
    """Create a subscription for an account on a plan."""
    return dump(commercial.subscribe(account, plan_key, seats=seats))


@mcp.tool()
def commercial_subscriptions(account: Optional[str] = None) -> str:
    """Active subscriptions (optionally for one account)."""
    rows = commercial.list_subscriptions(account)
    return dump({"count": len(rows), "subscriptions": [s.model_dump() for s in rows]})


@mcp.tool()
def commercial_meter_usage(account: str, tool: str, units: int = 1,
                           product: Optional[str] = None,
                           unit_price: Optional[float] = None) -> str:
    """Record a metered usage event (a billable MCP tool call) for an account."""
    return dump(commercial.meter_usage(account, tool, units=units, product=product,
                                       unit_price=unit_price))


@mcp.tool()
def commercial_usage(account: str, days: int = 30) -> str:
    """Usage summary for an account over a window, broken down by tool."""
    return dump(commercial.usage_summary(account, days=days))


@mcp.tool()
def commercial_bill(account: str, plan_key: Optional[str] = None, days: int = 30) -> str:
    """Build a usage-based billing statement (plan fee + overage + VAT) for an account."""
    return dump(commercial.bill_account(account, plan_key=plan_key, days=days))


@mcp.tool()
def commercial_revenue_share(commission_gross: float, platform_share: float = 0.20) -> str:
    """Performance revenue share: split a commission into platform and partner shares."""
    return dump(commercial.revenue_share(commission_gross,
                                         {"platform_share": platform_share,
                                          "partner_share": round(1 - platform_share, 4)}))


@mcp.tool()
def commercial_record_payout(transaction_id: str, gross_commission: float, payee: str,
                             share_pct: float, role: str = "agent") -> str:
    """Record a payee payout (agent / platform / agency) against a transaction commission."""
    payout = commercial.record_payout(transaction_id, gross_commission, payee, share_pct, role=role)
    return dump({"payout": payout.model_dump()})


@mcp.tool()
def commercial_payouts(account: Optional[str] = None, status: Optional[str] = None) -> str:
    """Recorded payouts, optionally filtered by payee or status."""
    rows = commercial.list_payouts(account=account, status=status)
    return dump({"count": len(rows), "payouts": [p.model_dump() for p in rows]})


@mcp.tool()
def commercial_gtm() -> str:
    """The go-to-market playbook: product prioritisation (P0–P2) and the four principles."""
    return dump(commercial.GTM_PLAYBOOK)


@mcp.tool()
def agentic_portal(lang: str = "en", theme: str = "auto") -> str:
    """Render the **Agentic OS** portal page (HTML): the product roadmap, the agent
    catalogue, live Smart Actions and recorded runs."""
    ov = agents.agentic_overview()
    actions = agents.prioritise_actions(_smart_action_signals(), limit=10)
    product_rows = [[p["priority"], p["name"], p["category"], p["agent_count"]]
                    for p in agents.agent_products()]
    agent_rows = [[a["name"], a["category"], a["autonomy"], a["priority"],
                   ", ".join(a["tools"][:4])] for a in sorted(agents.AGENTS, key=lambda x: x["category"])]
    action_rows = [[a["band"], a["title"], a["reason"] or "—", a["suggested_agent"] or "—"]
                   for a in actions["actions"]]
    run_rows = [[r.agent_key, r.status, len(r.steps)] for r in agents.runs_db[-10:]]
    sections: List[Dict[str, Any]] = [
        {"kind": "cards", "heading": "Agentic OS at a glance", "items": [
            ["Agents", ov["counts"]["agents"], "product + specialist"],
            ["Products", ov["counts"]["products"], "roadmap"],
            ["Autonomous", ov["counts"]["autonomous"], "no human in the loop"],
            ["Runs", ov["counts"]["runs_recorded"], "audited"],
            ["Smart actions", actions["count"], "prioritised"],
            ["Urgent", actions["by_band"]["urgent"], "do now"]]},
        {"kind": "text", "heading": "Positioning", "text": (
            "The portal is an Agentic Operating System: CRM, transactions, accounting, GIS, "
            "leasing and marketing agents act on one shared data layer, while every autonomous "
            "step is planned, approval-gated and audited. MCP comes first — the same tools an "
            "external AI client calls power these agents.")},
        {"kind": "html", "heading": "Interactive build-cost preview",
         "html": _construction_calculator_html()},
        {"kind": "table", "heading": "Product roadmap",
         "columns": ["Priority", "Product", "Category", "Agents"], "rows": product_rows},
        {"kind": "table", "heading": "Agent catalogue",
         "columns": ["Agent", "Category", "Autonomy", "Priority", "Bound tools"], "rows": agent_rows},
        {"kind": "table", "heading": "Smart Actions (today)",
         "columns": ["Band", "Action", "Reason", "Suggested agent"], "rows": action_rows},
        {"kind": "table", "heading": "Recent agent runs",
         "columns": ["Agent", "Status", "Steps"], "numeric": ["Steps"], "rows": run_rows},
    ]
    ads = content.ad_section(slot="banner", category="smart_technology", lang=lang)
    if ads.get("count"):
        sections.append(ads)
    return gis.build_report_html(title="Agentic OS",
                                 subtitle="Agents · products · smart actions · audited runs",
                                 sections=sections, ticker_html=_portal_ticker(lang),
                                 lang=lang, theme=theme)


@mcp.tool()
def commercial_portal(lang: str = "en", theme: str = "auto") -> str:
    """Render the **Commercialization wing** portal page (HTML): product catalogue, pricing
    matrix, representative plans and the GTM playbook."""
    matrix = commercial.pricing_matrix()
    prod_rows = [[p["priority"], p["name"], p["segment"], ", ".join(p["pricing_models"]),
                  f"{p['price_from']:,.0f} {p['unit']}"] for p in commercial.PRODUCTS]
    plan_rows = [[pl["name"], pl["product"], f"{pl['price']:,.0f}", pl["interval"],
                  f"{pl['included_units']:,}", f"{pl['overage_rate']}"] for pl in commercial.PLANS]
    gtm_rows = [[p["tier"], p["product"], p["reason"]] for p in commercial.GTM_PLAYBOOK["priorities"]]
    principle_rows = [[p["name"], p["detail"]] for p in commercial.GTM_PLAYBOOK["principles"]]
    sections: List[Dict[str, Any]] = [
        {"kind": "cards", "heading": "Commercialization at a glance", "items": [
            ["Products", len(commercial.PRODUCTS), "P0–P2"],
            ["Pricing models", len(commercial.PRICING_MODELS), "hybrid"],
            ["Plans", len(commercial.PLANS), "subscription + usage"],
            ["Subscriptions", len(commercial.subscriptions_db), "active"],
            ["Meter events", len(commercial.meter_events_db), "billable calls"],
            ["Payouts", len(commercial.payouts_db), "performance share"]]},
        {"kind": "text", "heading": "Pricing philosophy", "text": (
            "Pricing is hybrid: a predictable subscription base, usage-based metering per MCP "
            "tool call or per qualified lead, and a performance share on closings and rent — "
            "predictable ARR with upside, monetising from day one.")},
        {"kind": "table", "heading": "Products & positioning",
         "columns": ["Priority", "Product", "Segment", "Models", "From"], "rows": prod_rows},
        {"kind": "table", "heading": "Representative plans",
         "columns": ["Plan", "Product", "Price", "Interval", "Included", "Overage"],
         "rows": plan_rows},
        {"kind": "table", "heading": "Go-to-market priorities",
         "columns": ["Tier", "Product", "Why"], "rows": gtm_rows},
        {"kind": "table", "heading": "GTM principles",
         "columns": ["Principle", "Detail"], "rows": principle_rows},
    ]
    ads = content.ad_section(slot="infeed", category="smart_technology", lang=lang)
    if ads.get("count"):
        sections.append(ads)
    return gis.build_report_html(title="Commercialization wing",
                                 subtitle="Products · hybrid pricing · metering · payouts",
                                 sections=sections, ticker_html=_portal_ticker(lang),
                                 lang=lang, theme=theme)


# ---------- Agentic OS resources ----------


@mcp.resource("agents://overview", name="Agentic overview",
              description="Counts, products and autonomy mix of the Agentic OS.")
def res_agents_overview() -> str:
    return agents_overview()


@mcp.resource("agents://catalog", name="Agent catalogue",
              description="All product agents and specialist sub-agents.")
def res_agents_catalog() -> str:
    return agents_catalog()


@mcp.resource("agents://products", name="Agent products",
              description="The eight roadmap products and their agent modules.")
def res_agents_products() -> str:
    return agent_products()


@mcp.resource("agents://runs", name="Agent runs",
              description="Recorded agent runs (audit trail).")
def res_agents_runs() -> str:
    return agent_runs()


@mcp.resource("agents://smart-actions", name="Smart actions",
              description="Prioritised human-in-the-loop action list.")
def res_agents_smart_actions() -> str:
    return agent_smart_actions()


@mcp.resource("agent://{key}", name="Agent definition", description="One agent by key.")
def res_agent(key: str) -> str:
    return agent_get(key)


# ---------- Transaction resources ----------


@mcp.resource("transactions://all", name="All transactions",
              description="Every recorded transaction.")
def res_transactions() -> str:
    return transactions_list()


@mcp.resource("transactions://deadlines", name="Transaction deadlines",
              description="All transaction milestones due soon.")
def res_transaction_deadlines() -> str:
    return transaction_deadlines()


@mcp.resource("transaction://{tx_id}", name="Transaction",
              description="One transaction with milestones, offers and signatures.")
def res_transaction(tx_id: str) -> str:
    return transaction_get(tx_id)


# ---------- Intelligence resources ----------


@mcp.resource("intelligence://anomalies", name="Price anomalies",
              description="Z-score underpriced / overpriced listings by area.")
def res_intel_anomalies() -> str:
    return buyer_anomaly_scan()


@mcp.resource("intelligence://screener", name="Investment screener",
              description="Risk-adjusted screening of the live listing book.")
def res_intel_screener() -> str:
    return investment_screen()


# ---------- Leasing resources ----------


@mcp.resource("leasing://units", name="Rental units",
              description="Rental units with rents and cost floors.")
def res_leasing_units() -> str:
    return leasing_units()


@mcp.resource("leasing://funnel", name="Leasing funnel",
              description="Inquiry auto-handling and application funnel.")
def res_leasing_funnel() -> str:
    return leasing_funnel()


@mcp.resource("leasing://inquiries", name="Leasing inquiries",
              description="Handled leasing inquiries.")
def res_leasing_inquiries() -> str:
    return leasing_inquiries()


# ---------- Marketing resources ----------


@mcp.resource("marketing://routes", name="Lead routes",
              description="Lead-routing rules.")
def res_marketing_routes() -> str:
    return marketing_routes()


@mcp.resource("marketing://funnel", name="Marketing funnel",
              description="Lead funnel by stage, band and channel.")
def res_marketing_funnel() -> str:
    return marketing_funnel()


@mcp.resource("marketing://content", name="Content assets",
              description="Generated marketing content assets.")
def res_marketing_content() -> str:
    return marketing_content_assets()


# ---------- Commercialization resources ----------


@mcp.resource("commercial://products", name="Products",
              description="Commercial product catalogue.")
def res_commercial_products() -> str:
    return commercial_products()


@mcp.resource("commercial://plans", name="Plans",
              description="Subscription and usage plans.")
def res_commercial_plans() -> str:
    return commercial_plans()


@mcp.resource("commercial://pricing", name="Pricing matrix",
              description="Hybrid pricing matrix and GTM playbook.")
def res_commercial_pricing() -> str:
    return commercial_pricing_matrix()


@mcp.resource("commercial://subscriptions", name="Subscriptions",
              description="Active subscriptions.")
def res_commercial_subscriptions() -> str:
    return commercial_subscriptions()


@mcp.resource("commercial://gtm", name="GTM playbook",
              description="Prioritisation and go-to-market principles.")
def res_commercial_gtm() -> str:
    return commercial_gtm()


# ---------- Prompts for the agentic products ----------


@mcp.prompt(name="conversational_buyer_brief",
            description="Run the conversational buyer agent from a natural-language brief.")
def prompt_buyer_brief(brief: str = "budget 3 crore, commute under 35 minutes, good schools") -> str:
    return (
        "You are the Conversational Homebuying Agent for the portal.\n"
        f"Buyer brief: {brief}\n\n"
        "1. Call buyer_parse_requirement to structure the brief.\n"
        "2. Call buyer_recommend for a scored shortlist with reasons.\n"
        "3. Call buyer_anomaly_scan to surface below-market bargains.\n"
        "4. Call buyer_affordability for the monthly outlay and DTI.\n"
        "5. Present a short, plain-language recommendation and offer to schedule viewings."
    )


@mcp.prompt(name="seller_pricing_listing",
            description="Run the seller pricing & marketing agent for a property.")
def prompt_seller_listing(property_id: str) -> str:
    return (
        "You are the Seller Intelligent Pricing & Marketing Agent.\n"
        f"Property id: {property_id}\n\n"
        "1. Call seller_cma for an adjusted-comp price range and confidence.\n"
        "2. Call seller_net_proceeds at the target price.\n"
        "3. Call seller_marketing_assets for the marketing kit.\n"
        "4. Call seller_report to render the client-ready HTML report."
    )


@mcp.prompt(name="transaction_close_prompt",
            description="Guide a transaction from terms to closing on the ledger.")
def prompt_transaction_close(tx_id: str) -> str:
    return (
        "You are the Transaction Agent.\n"
        f"Transaction id: {tx_id}\n\n"
        "1. Call transaction_get, then transaction_extract_terms on any contract text.\n"
        "2. Call transaction_deadlines and transaction_progress to find risk.\n"
        "3. Call transaction_offer_add / transaction_offer_respond as offers arrive.\n"
        "4. Call transaction_signature_add until transaction_signatures reports complete.\n"
        "5. Call transaction_close to post the balanced journal entry and record payouts."
    )


@mcp.prompt(name="agentic_workspace_brief",
            description="Produce a broker's morning brief from the Agentic OS.")
def prompt_agentic_workspace() -> str:
    return (
        "You are the Broker AI Workspace.\n"
        "1. Call agent_smart_actions for the prioritised morning brief.\n"
        "2. Call transaction_deadlines for near-term risk.\n"
        "3. Call agent_move_likelihood on the warmest contacts.\n"
        "4. Call commercial_usage to show the broker's metered usage this month.\n"
        "5. Summarise the three highest-impact actions and offer to draft outreach."
    )


@mcp.prompt(name="investment_screener_prompt",
            description="Screen the market into risk-adjusted investment picks.")
def prompt_investment_screener(city: str = "Lahore", min_cap_rate: str = "0.05") -> str:
    return (
        "You are the Agentic Investment Screener.\n"
        f"City: {city}, minimum cap rate: {min_cap_rate}\n\n"
        "1. Call investment_screen with the criteria.\n"
        "2. Call investment_underwrite on the top pick for the full return set.\n"
        "3. Call investment_portfolio_alerts for exit/refinance signals.\n"
        "4. Call investment_report to render the HTML report."
    )


# ============================================================
# ====== PRODUCT SURFACES: MCP-for-brokers & Property Intelligence ======
# ============================================================
#
# The Agentic-OS catalogue binds these tool names to its P0 products
# ("mcp_for_brokers", "property_intelligence_mcp"). They are the *productised
# front doors* over engines that already exist — one implementation, reachable
# from MCP and REST alike.


def _contact_from_id(contact_id: str) -> Optional[Dict[str, Any]]:
    """Resolve a contact id to a lead or customer profile for the broker CRM."""
    lead = next((l for l in leads_db if l.id == contact_id), None)
    if lead:
        return {"kind": "lead", "id": lead.id, "name": lead.name, "email": lead.email,
                "phone": lead.phone, "status": lead.status, "source": lead.source,
                "city": city_name(lead.city_id), "interest": lead.interest_category,
                "budget_max": lead.budget_max, "engagement_score": lead.score or 40,
                "assigned_agent_id": lead.assigned_agent_id}
    cust = next((c for c in customers_db if c.id == contact_id), None)
    if cust:
        return {"kind": "customer", "id": cust.id, "name": cust.name, "email": cust.email,
                "phone": cust.phone, "status": cust.type, "source": "crm",
                "city": city_name(cust.city_id), "interest": cust.type,
                "budget_max": None, "engagement_score": 55,
                "assigned_agent_id": cust.assigned_agent_id}
    return None


def _contact_days_since(contact_id: str) -> float:
    last = max((i.occurred_at for i in interactions_db if i.entity_id == contact_id), default=None)
    return max(0.0, float((datetime.now() - last).days)) if last else 90.0


@mcp.tool()
def search_contacts(query: Optional[str] = None, status: Optional[str] = None,
                    min_intent_score: Optional[float] = None,
                    lifecycle: Optional[str] = None, limit: int = 25) -> str:
    """Search CRM contacts with **live move-likelihood intent scoring**.

    The broker's "who should I call next" tool (product: *MCP for Brokers*). Filter by
    free-text ``query`` (name / e-mail / phone), CRM ``status``, a minimum
    ``min_intent_score`` (0–100), or a ``lifecycle`` bucket
    (``hot`` | ``warm`` | ``dormant`` | ``financially_ready``). Each row carries the
    scored profile, the reasons behind the score and the recommended next action.
    """
    rows: List[Dict[str, Any]] = []
    needle = (query or "").lower().strip()
    for l in leads_db:
        hay = " ".join(filter(None, [l.name, l.email, l.phone])).lower()
        if needle and needle not in hay:
            continue
        if status and l.status != status:
            continue
        feats = _lead_features(l)
        ml = agents.move_likelihood(feats)
        score = float(ml["score"])
        days = feats["days_since_contact"]
        if lifecycle == "hot" and ml["band"] not in ("very_high", "high"):
            continue
        if lifecycle == "warm" and ml["band"] != "medium":
            continue
        if lifecycle == "dormant" and days < 30:
            continue
        if lifecycle == "financially_ready" and not feats["financial_ready"]:
            continue
        if min_intent_score is not None and score < min_intent_score:
            continue
        rows.append({
            "id": l.id, "name": l.name, "email": l.email, "phone": l.phone,
            "status": l.status, "source": l.source, "city": city_name(l.city_id),
            "budget_max": l.budget_max, "intent_score": score, "band": ml["band"],
            "lifecycle": ("dormant" if days >= 30 else ml["band"]),
            "days_since_contact": round(days, 1),
            "recommended_action": ml["recommended_action"], "reasons": ml["reasons"],
        })
    rows.sort(key=lambda r: -r["intent_score"])
    capped = rows[: max(1, int(limit))]
    return dump({"count": len(rows), "returned": len(capped), "query": query,
                 "lifecycle": lifecycle, "min_intent_score": min_intent_score,
                 "contacts": capped})


@mcp.tool()
def get_commission_projection(agent_id: Optional[str] = None, horizon_days: int = 90,
                              commission_rate: float = 0.02) -> str:
    """Project commission from the live deal pipeline and the near-term closing schedule.

    A *MCP for Brokers* revenue tool. Returns realised (closed-won) commission, the
    probability-weighted pipeline, the expected total, the closings inside
    ``horizon_days``, and the split by agent and by pipeline stage.
    """
    today = datetime.now()
    closed = 0.0
    weighted = 0.0
    upcoming: List[Dict[str, Any]] = []
    by_agent: Dict[str, float] = {}
    by_stage: Dict[str, float] = {}
    for d in deals_db:
        if agent_id and d.agent_id != agent_id:
            continue
        if d.stage == "closed_won":
            closed += d.commission or (d.amount or 0.0) * commission_rate
            continue
        if d.stage == "closed_lost":
            continue
        proj = (d.amount or 0.0) * (d.probability / 100.0) * commission_rate
        weighted += proj
        by_stage[d.stage] = round(by_stage.get(d.stage, 0.0) + proj, 2)
        aid = d.agent_id or "unassigned"
        by_agent[aid] = round(by_agent.get(aid, 0.0) + proj, 2)
        if d.expected_close_date:
            try:
                due = datetime.strptime(d.expected_close_date, "%Y-%m-%d")
            except ValueError:
                continue
            days_left = (due - today).days
            if 0 <= days_left <= horizon_days:
                upcoming.append({"deal_id": d.id, "title": d.title, "amount": d.amount,
                                 "stage": d.stage, "probability": d.probability,
                                 "days_to_close": days_left,
                                 "commission": round((d.amount or 0.0) * commission_rate, 2),
                                 "weighted_commission": round(proj, 2),
                                 "agent_id": d.agent_id})
    upcoming.sort(key=lambda r: r["days_to_close"])
    return dump({
        "agent_id": agent_id, "horizon_days": horizon_days, "commission_rate": commission_rate,
        "closed_commission": round(closed, 2),
        "weighted_pipeline_commission": round(weighted, 2),
        "expected_total": round(closed + weighted, 2),
        "upcoming_closings": upcoming,
        "by_agent": by_agent, "by_stage": by_stage,
    })


def _gis_score_impl(property_id: Optional[str] = None, address: Optional[str] = None,
                    destination: Optional[str] = None) -> Dict[str, Any]:
    """Shared GIS scoring used by ``analyze_property_gis`` and ``get_gis_score``."""
    p = find_property(property_id) if property_id else None
    if p is None and address:
        t = address.strip().lower()
        p = next((x for x in properties_db if t and t in (x.title or "").lower()), None)
        if p is None:
            c = resolve_city(address)
            if c:
                p = next((x for x in properties_db if x.city_id == c.id), None)
    if p is None:
        p = properties_db[0] if properties_db else None
    if p is None:
        return {"error": "no property found"}
    dest = _resolve_commute_point(destination)
    ctx = _candidate_context({}, p, dest)
    dims = {
        "amenities": round(float(ctx.get("amenities_score", 0.0)), 1),
        "schools": round(float(ctx.get("schools_score", 0.0)), 1),
        "safety": round(float(ctx.get("safety_score", 0.0)), 1),
    }
    cm = ctx.get("commute_minutes")
    if cm is not None:
        dims["commute"] = round(max(0.0, 100.0 - float(cm) * 1.5), 1)
    composite = round(sum(dims.values()) / len(dims), 1) if dims else 0.0
    grade = "A" if composite >= 80 else "B" if composite >= 65 else "C" if composite >= 50 else "D"
    return {
        "property_id": p.id, "title": p.title, "city": city_name(p.city_id),
        "scheme": _scheme_label(p.scheme_id),
        "coordinates": {"lat": p.latitude, "lng": p.longitude},
        "dimensions": dims, "composite_score": composite, "grade": grade,
        "poi_counts": ctx.get("poi_counts", {}),
        "commute_km": ctx.get("commute_km"), "commute_minutes": cm,
        "commute_destination": destination or ("city centre" if cm is not None else None),
        "narrative": f"{grade} location — composite {composite}/100 across "
                     f"{', '.join(sorted(dims))}.",
    }


@mcp.tool()
def analyze_property_gis(property_id: Optional[str] = None, address: Optional[str] = None,
                         commute_destination: Optional[str] = None) -> str:
    """GIS-enhanced property analysis: amenity, school, safety and commute scores.

    A *MCP for Brokers* tool. Supply a ``property_id`` (preferred) or a free-text
    ``address``. Optionally give a ``commute_destination`` (a POI name, e.g. a business
    district) to score the daily commute. Returns the dimensions, a composite 0–100
    score, a letter grade and the nearby-POI counts.
    """
    return dump(_gis_score_impl(property_id, address, commute_destination))


@mcp.tool()
def get_gis_score(property_id: Optional[str] = None, address: Optional[str] = None,
                  destination: Optional[str] = None) -> str:
    """The *Property Intelligence* "GIS score" for an address or property (0–100 + grade).

    A pay-per-call tool for external AI clients: returns the multi-dimensional location
    score behind the portal's ranking (amenities, schools, safety, commute).
    """
    return dump(_gis_score_impl(property_id, address, destination))


@mcp.tool()
def get_accounting_snapshot(property_id: str, rental_yield: float = 0.045,
                            operating_expense_rate: float = 0.30) -> str:
    """Accounting snapshot for one property: value, income, NOI, cap rate and leverage ROI.

    A *Property Intelligence* pay-per-call tool that points the portal's accounting
    engine at a single asset. Estimates gross rent from ``rental_yield`` and operating
    expenses from ``operating_expense_rate``, then reports NOI, cap rate, gross/net
    yield and a leveraged ROI, alongside any active leases on the property.
    """
    p = find_property(property_id)
    if not p:
        return dump({"error": f"Unknown property: {property_id}"})
    price = float(p.price or 0.0)
    annual_rent = round(price * rental_yield, 2)
    expenses = round(annual_rent * operating_expense_rate, 2)
    noi = round(annual_rent - expenses, 2)
    roi = accounting.property_roi(price, annual_rent=annual_rent, annual_expenses=expenses,
                                  down_payment_share=0.25, loan_rate=0.16, loan_years=20)
    leases = accounting.list_leases(status="active", property_id=property_id)
    contracted = round(sum(float(l.get("annual_rent") or 0.0) for l in leases), 2)
    return dump({
        "property_id": p.id, "title": p.title, "city": city_name(p.city_id),
        "category": p.category,
        "value": price,
        "assumed_gross_yield": rental_yield,
        "estimated_annual_rent": annual_rent,
        "estimated_annual_expenses": expenses,
        "net_operating_income": noi,
        "cap_rate": round(noi / price, 4) if price else 0.0,
        "active_leases": len(leases), "contracted_annual_rent": contracted,
        "roi": roi if "error" not in roi else None,
    })


@mcp.tool()
def get_market_intelligence(region: Optional[str] = None, years: int = 5) -> str:
    """Regional market intelligence — pricing, factor index, news momentum and a forecast.

    A *Property Intelligence* pay-per-call tool. ``region`` is a city name (omit for the
    national view). Composites the development, infrastructure, economic, social,
    political, regulatory and demand factors with live news sentiment into a directional
    read and a recommendation.
    """
    trends = json.loads(market_trends(city=region, years=years))
    index = (trends.get("factors") or {}).get("index") or {}
    idx = float(index.get("composite") or 0.0)
    direction = "expanding" if idx >= 60 else "stable" if idx >= 45 else "softening"
    return dump({
        "region": region or "national",
        "market_index": index,
        "direction": direction,
        "pricing": trends.get("pricing"),
        "supply": trends.get("supply"),
        "forecast": trends.get("forecast"),
        "yield": trends.get("yield"),
        "factors": (trends.get("factors") or {}).get("scores") or {},
        "news_momentum": trends.get("news") or {},
        "recommendation": {
            "expanding": "favour acquisition — expect price growth and tightening supply",
            "stable": "balanced market — negotiate on condition and terms",
            "softening": "favour buyers/renters — underwrite with a wider margin",
        }[direction],
    })


@mcp.tool()
def score_seller_intent(contact_id: str, equity_pct: Optional[float] = None,
                        holding_years: Optional[float] = None, market_heat: float = 0.6,
                        life_event: Optional[str] = None, fsbo_signal: bool = False) -> str:
    """Score how likely a CRM contact is to **sell** (0–100), with reasons and next action.

    A *Property Intelligence* pay-per-call tool. Resolves the contact (a lead or
    customer id) and derives seller-intent features, any of which you may override:
    owned ``equity_pct``, ``holding_years``, ``market_heat`` (0–1), a ``life_event``
    string, and an ``fsbo_signal`` (listed privately).
    """
    contact = _contact_from_id(contact_id)
    if not contact:
        return dump({"error": f"Unknown contact: {contact_id}",
                     "hint": "pass a lead or customer id"})
    days = _contact_days_since(contact_id)
    feats = {
        "equity_pct": equity_pct if equity_pct is not None
        else (55.0 if contact["kind"] == "customer" else 35.0),
        "holding_years": holding_years if holding_years is not None else 6.0,
        "market_heat": market_heat, "life_event": life_event,
        "fsbo_signal": fsbo_signal,
        "engagement_score": contact.get("engagement_score") or 40,
    }
    out = agents.seller_intent_score(feats)
    out["contact"] = contact
    out["days_since_contact"] = round(days, 1)
    out["features"] = feats
    return dump(out)


@mcp.tool()
def create_listing_draft(property_id: str, tone: str = "professional", lang: str = "en") -> str:
    """Draft a complete listing kit for a property.

    A *MCP for Brokers* tool. Returns the headline, description, bullet highlights,
    per-channel social posts, an e-mail, a short video script, staging notes and
    hashtags. The draft is returned for review — publishing stays human-approved.
    """
    p = find_property(property_id)
    if not p:
        return dump({"error": f"Unknown property: {property_id}"})
    features: List[str] = []
    if p.bedrooms:
        features.append(f"{p.bedrooms} bedrooms")
    if p.bathrooms:
        features.append(f"{p.bathrooms} bathrooms")
    if p.floors:
        features.append(f"{p.floors} floors")
    if p.covered_area:
        features.append(f"{p.covered_area:,.0f} sqft covered")
    assets = intelligence.generate_listing_assets({
        "id": p.id, "title": p.title, "city": city_name(p.city_id),
        "scheme": _scheme_label(p.scheme_id), "price": p.price,
        "covered_area": p.covered_area or p.plot_area, "plot_area": p.plot_area,
        "bedrooms": p.bedrooms, "category": p.category, "features": features,
    }, lang=lang, tone=tone)
    return dump({"property_id": p.id, "status": "draft", **assets})


@mcp.resource("broker://contacts", name="Broker contacts",
              description="CRM contacts with live move-likelihood intent scoring.")
def res_broker_contacts() -> str:
    return search_contacts()


@mcp.resource("broker://commission-projection", name="Commission projection",
              description="Weighted commission pipeline for the broker workspace.")
def res_broker_commission() -> str:
    return get_commission_projection()


@mcp.resource("property-intelligence://market", name="Market intelligence",
              description="National market intelligence for the Property Intelligence product.")
def res_property_market() -> str:
    return get_market_intelligence()


@mcp.resource("property-intelligence://gis/{property_id}", name="Property GIS score",
              description="Multi-dimensional GIS score for a property.")
def res_property_gis(property_id: str) -> str:
    return get_gis_score(property_id=property_id)


# ============================================================
# ====== PORTAL: discovery, health, settings, federated search ======
# ============================================================

MODEL_REGISTRY: Dict[str, Any] = {
    "city": City, "scheme": HousingScheme, "block": BlockZoneArea, "property": Property,
    "bigproject": BigProject, "agent": Agent, "lead": Lead, "customer": Customer,
    "interaction": Interaction, "deal": Deal, "task": Task, "appointment": Appointment,
    "news": NewsItem, "market_factor": MarketFactor, "poi": PointOfInterest,
    "aoi": AreaOfInterest, "account": accounting.Account, "journal_entry": accounting.JournalEntry,
    "invoice": accounting.Invoice, "payment": accounting.Payment, "expense": accounting.Expense,
    "lease": accounting.Lease, "budget": accounting.Budget,
    "page": content.PortalPage, "history": content.HistoryEntry, "contact": content.ContactChannel,
    "success_story": content.SuccessStory, "advertisement": content.Advertisement,
    "construction_estimate": construction.ConstructionEstimate,
    "maintenance_plan": maintenance.MaintenancePlan, "work_order": maintenance.WorkOrder,
    "agent_run": agents.AgentRun, "agent_step": agents.AgentStep,
    "transaction": transactions.Transaction, "offer": transactions.Offer,
    "signature": transactions.Signature, "contract_term": transactions.ContractTerm,
    "rental_unit": leasing.RentalUnit, "rental_inquiry": leasing.RentalInquiry,
    "application": leasing.Application,
    "marketing_lead": marketing.MarketingLead, "lead_route": marketing.LeadRoute,
    "content_asset": marketing.ContentAsset, "campaign": marketing.Campaign,
    "subscription": commercial.Subscription, "meter_event": commercial.MeterEvent,
    "payout": commercial.Payout, "tool_project": tools.SavedToolProject,
    "pm_project": pmo.PMProject, "pm_task": pmo.PmTask, "pm_phase": pmo.PmPhase,
    "pm_milestone": pmo.PmMilestone, "pm_resource": pmo.PmResource,
    "pm_cost_entry": pmo.PmCostEntry, "pm_risk": pmo.PmRisk,
    "pm_change_request": pmo.PmChangeRequest, "pm_site_log": pmo.PmSiteLog,
    "pm_inspection": pmo.PmInspection, "pm_action": pmo.PmAction,
    "conversation": messaging.Conversation, "membership": messaging.Membership,
    "message": messaging.Message, "attachment": messaging.Attachment,
    "message_action": messaging.MessageAction, "notification_record": messaging.NotificationRecord,
    "outbox_item": messaging.OutboxItem, "telegram_link": messaging.TelegramLink,
    "audit_event": messaging.AuditEvent, "message_report": messaging.MessageReport,
    "msg_profile": messaging.MsgProfile,
}


def _tool_group(name: str) -> str:
    prefixes = [
        ("accounting_", "accounting"), ("finance_", "finance"), ("auth_", "authentication"),
        ("poi_", "poi"), ("aoi_", "aoi"), ("gis_", "gis"), ("crm_", "crm"),
        ("portal_", "portal"), ("news_", "news"), ("memory_", "memory"),
        ("content_", "content"), ("ad_", "advertising"), ("ads_", "advertising"),
        ("construction_", "construction"), ("maintenance_", "maintenance"),
        ("agents_", "agents"), ("agent_", "agents"), ("agentic_", "agents"),
        ("transactions_", "transactions"), ("transaction_", "transactions"),
        ("buyer_", "intelligence"), ("seller_", "intelligence"), ("investment_", "investment"),
        ("leasing_", "leasing"), ("marketing_", "marketing"), ("commercial_", "commercial"),
        # Productised front doors (MCP-for-brokers / Property Intelligence):
        ("search_contacts", "crm"), ("score_seller_intent", "crm"),
        ("get_commission_projection", "crm"), ("create_listing_draft", "intelligence"),
        ("analyze_property_gis", "gis"), ("get_gis_score", "gis"),
        ("get_accounting_snapshot", "accounting"), ("get_market_intelligence", "market"),
        ("tools_", "tools"), ("tool_", "tools"),
        ("pmo_", "pmo"), ("pm_", "pmo"),
        ("msg_", "messaging"), ("messaging_", "messaging"),
        ("image_", "images"), ("rag_", "rag"), ("add_", "hierarchy"),
        ("update_", "hierarchy"), ("delete_", "hierarchy"), ("get_", "hierarchy"),
        ("list_", "hierarchy"), ("search_", "search"),
    ]
    for prefix, group in prefixes:
        if name.startswith(prefix):
            return group
    return "general"


def _settings_snapshot() -> Dict[str, Any]:
    return {
        "assumptions": GIS_ASSUMPTIONS,
        "forecast": {
            "base_price_cagr": BASE_PRICE_CAGR, "growth_sensitivity": GROWTH_SENSITIVITY,
            "cost_inflation_cagr": COST_INFLATION_CAGR, "default_build_years": DEFAULT_BUILD_YEARS,
            "land_cost_share": LAND_COST_SHARE,
        },
        "factor_weights": FACTOR_WEIGHTS,
        "scenarios": SCENARIOS,
        "accounting": accounting.ACCOUNTING_CONFIG,
        "auth": auth.AUTH_CONFIG,
        "content": content.CONTENT_CONFIG,
        "advertising": content.ADS_CONFIG,
        "construction": construction.CONSTRUCTION_CONFIG,
        "maintenance": maintenance.MAINTENANCE_CONFIG,
        "agentic": agents.AGENTIC_CONFIG,
        "transactions": transactions.TRANSACTION_CONFIG,
        "intelligence": {"buyer_weights": intelligence.BUYER_WEIGHTS,
                         "anomaly_z_threshold": intelligence.ANOMALY_Z_THRESHOLD},
        "leasing": leasing.LEASING_CONFIG,
        "marketing": marketing.MARKETING_CONFIG,
        "commercial": commercial.COMMERCIAL_CONFIG,
        "tools": tools.TOOLS_CONFIG,
        "pmo": pmo.PMO_CONFIG,
        "messaging": messaging.MESSAGING_CONFIG,
    }


@mcp.tool()
def portal_health() -> str:
    """Liveness snapshot: version, store counts and registered MCP surface size."""
    return dump(
        {
            "status": "ok",
            "version": SERVER_VERSION,
            "mcp": {
                "tools": len(mcp._tool_manager.list_tools()),
                "resources": len(mcp._resource_manager.list_resources()),
                "resource_templates": len(mcp._resource_manager.list_templates()),
                "prompts": len(mcp._prompt_manager.list_prompts()),
            },
            "stores": {
                "cities": len(cities_db), "schemes": len(housing_schemes_db),
                "blocks": len(block_zone_areas_db), "properties": len(properties_db),
                "big_projects": len(big_projects_db), "agents": len(agents_db), "leads": len(leads_db),
                "customers": len(customers_db), "deals": len(deals_db), "news": len(news_db),
                "pois": len(pois_db), "aois": len(aois_db),
                "accounts": len(accounting.accounts_db), "journal_entries": len(accounting.journal_db),
                "invoices": len(accounting.invoices_db), "leases": len(accounting.leases_db),
                "pages": len(content.pages_db), "history": len(content.history_db),
                "contacts": len(content.contacts_db), "success_stories": len(content.stories_db),
                "advertisements": len(content.ads_db),
                "construction_estimates": len(construction.estimates_db),
                "maintenance_plans": len(maintenance.plans_db),
                "work_orders": len(maintenance.work_orders_db),
                "agent_runs": len(agents.runs_db),
                "transactions": len(transactions.transactions_db),
                "offers": len(transactions.offers_db),
                "rental_units": len(leasing.units_db),
                "leasing_inquiries": len(leasing.inquiries_db),
                "marketing_leads": len(marketing.leads_db),
                "content_assets": len(marketing.assets_db),
                "subscriptions": len(commercial.subscriptions_db),
                "meter_events": len(commercial.meter_events_db),
                "tool_projects": len(tools.projects_db),
                "pm_projects": len(pmo.projects_db), "pm_tasks": len(pmo.tasks_db),
                "pm_risks": len(pmo.risks_db), "pm_cost_entries": len(pmo.cost_entries_db),
                "msg_conversations": len(messaging.conversations_db),
                "msg_messages": len(messaging.messages_db),
                "msg_attachments": len(messaging.attachments_db),
                "msg_notifications": len(messaging.notifications_db),
                "msg_outbox": len(messaging.outbox_db),
                "msg_actions": len(messaging.actions_db),
                "msg_telegram_links": len(messaging.telegram_db),
            },
        }
    )


@mcp.tool()
def portal_catalog(include_parameters: bool = False, group: Optional[str] = None) -> str:
    """Full inventory of the MCP surface (tools / resources / templates / prompts), grouped.

    The REST layer mirrors this same surface — see ``fastapi_info``.
    """
    tools = []
    for t in sorted(mcp._tool_manager.list_tools(), key=lambda x: x.name):
        g = _tool_group(t.name)
        if group and g != group:
            continue
        row = {"name": t.name, "group": g,
               "description": (t.description or "").split("\n")[0].strip()}
        if include_parameters:
            row["parameters"] = sorted((t.parameters or {}).get("properties", {}).keys())
        tools.append(row)
    groups: Dict[str, int] = {}
    for row in tools:
        groups[row["group"]] = groups.get(row["group"], 0) + 1
    resources = [
        {"uri": r.uri, "name": r.name, "description": r.description}
        for r in sorted(mcp._resource_manager.list_resources(), key=lambda x: x.uri)
    ]
    templates = [
        {"uri_template": getattr(t, "uri_template", None), "name": getattr(t, "name", None),
         "description": getattr(t, "description", None)}
        for t in sorted(mcp._resource_manager.list_templates(), key=lambda x: str(getattr(x, "uri_template", "")))
    ]
    prompts = [
        {"name": p.name, "description": p.description}
        for p in sorted(mcp._prompt_manager.list_prompts(), key=lambda x: x.name)
    ]
    return dump(
        {
            "tool_count": len(tools),
            "groups": dict(sorted(groups.items())),
            "resources_count": len(resources),
            "templates_count": len(templates),
            "prompts_count": len(prompts),
            "tools": tools,
            "resources": resources,
            "resource_templates": templates,
            "prompts": prompts,
        }
    )


@mcp.tool()
def portal_schema(model: Optional[str] = None) -> str:
    """JSON schema for a portal model (city, property, deal, invoice, poi, aoi …) or the model list."""
    if not model:
        return dump({"models": sorted(MODEL_REGISTRY)})
    key = model.lower()
    cls = MODEL_REGISTRY.get(key)
    if cls is None:
        return dump({"error": f"Unknown model: {model}", "models": sorted(MODEL_REGISTRY)})
    return dump({"model": key, "schema": cls.model_json_schema()})


@mcp.tool()
def portal_settings(action: str = "get", updates: Optional[Dict[str, Any]] = None) -> str:
    """Read or edit runtime settings.

    ``action='update'`` accepts
    ``{assumptions|forecast|accounting|auth|agentic|transactions|intelligence|leasing|marketing|commercial|construction|maintenance|tools|pmo|messaging: {key: value}}``.
    """
    global BASE_PRICE_CAGR, GROWTH_SENSITIVITY, COST_INFLATION_CAGR, DEFAULT_BUILD_YEARS, LAND_COST_SHARE
    if action == "get":
        return dump(_settings_snapshot())
    if action != "update":
        return dump({"error": "action must be 'get' or 'update'"})
    if not updates:
        return dump({"error": "Provide updates as {assumptions|forecast|accounting|auth: {key: value}}"})
    applied: Dict[str, Any] = {}

    for key, value in (updates.get("assumptions") or {}).items():
        if key not in GIS_ASSUMPTIONS:
            continue
        if isinstance(GIS_ASSUMPTIONS[key], dict) and isinstance(value, dict):
            GIS_ASSUMPTIONS[key].update(value)
        else:
            GIS_ASSUMPTIONS[key] = value
        applied[f"assumptions.{key}"] = value

    forecast_map = {
        "base_price_cagr": "BASE_PRICE_CAGR", "growth_sensitivity": "GROWTH_SENSITIVITY",
        "cost_inflation_cagr": "COST_INFLATION_CAGR", "default_build_years": "DEFAULT_BUILD_YEARS",
        "land_cost_share": "LAND_COST_SHARE",
    }
    for key, value in (updates.get("forecast") or {}).items():
        if key not in forecast_map:
            continue
        if key == "base_price_cagr":
            BASE_PRICE_CAGR = float(value)
        elif key == "growth_sensitivity":
            GROWTH_SENSITIVITY = float(value)
        elif key == "cost_inflation_cagr":
            COST_INFLATION_CAGR = float(value)
        elif key == "default_build_years":
            DEFAULT_BUILD_YEARS = int(value)
        elif key == "land_cost_share":
            LAND_COST_SHARE = float(value)
        applied[f"forecast.{key}"] = value

    for key, value in (updates.get("accounting") or {}).items():
        if key in accounting.ACCOUNTING_CONFIG:
            accounting.ACCOUNTING_CONFIG[key] = value
            applied[f"accounting.{key}"] = value

    for key, value in (updates.get("auth") or {}).items():
        if key in auth.AUTH_CONFIG:
            auth.AUTH_CONFIG[key] = value
            applied[f"auth.{key}"] = value

    for group, config in (("agentic", agents.AGENTIC_CONFIG),
                          ("transactions", transactions.TRANSACTION_CONFIG),
                          ("leasing", leasing.LEASING_CONFIG),
                          ("marketing", marketing.MARKETING_CONFIG),
                          ("commercial", commercial.COMMERCIAL_CONFIG),
                          ("construction", construction.CONSTRUCTION_CONFIG),
                          ("maintenance", maintenance.MAINTENANCE_CONFIG),
                          ("tools", tools.TOOLS_CONFIG),
                          ("pmo", pmo.PMO_CONFIG),
                          ("messaging", messaging.MESSAGING_CONFIG)):
        for key, value in (updates.get(group) or {}).items():
            if key in config:
                config[key] = value
                applied[f"{group}.{key}"] = value

    for key, value in (updates.get("intelligence") or {}).items():
        if key == "anomaly_z_threshold":
            intelligence.ANOMALY_Z_THRESHOLD = float(value)
            applied["intelligence.anomaly_z_threshold"] = value
        elif key == "buyer_weights" and isinstance(value, dict):
            intelligence.BUYER_WEIGHTS.update(value)
            applied["intelligence.buyer_weights"] = value

    return dump({"updated": applied, "settings": _settings_snapshot()})


@mcp.tool()
def portal_audit_log(limit: int = 50) -> str:
    """Unified activity trail: memory cache, authentication events and recent ledger postings."""
    return dump(
        {
            "memory": near_memory_cache[-limit:],
            "auth_events": auth.list_events(limit=limit),
            "journal_entries": accounting.list_journal_entries(limit=limit),
            "counts": {
                "memory": len(near_memory_cache),
                "auth_events": len(auth.auth_events_db),
                "journal_entries": len(accounting.journal_db),
            },
        }
    )


@mcp.tool()
def global_search(query: str, limit: int = 10) -> str:
    """Federated search across the whole portal: hierarchy, projects, POIs, AOIs, news, CRM and tools."""
    q = (query or "").strip().lower()
    if not q:
        return dump({"error": "query is required"})

    def has(*values: Any) -> bool:
        return any(q in str(v).lower() for v in values if v)

    results: Dict[str, List[Dict[str, Any]]] = {
        "cities": [], "schemes": [], "blocks": [], "properties": [], "big_projects": [],
        "pois": [], "areas_of_interest": [], "news": [], "agents": [], "leads": [],
        "customers": [], "deals": [], "pages": [], "advertisements": [],
        "construction_techniques": [], "construction_materials": [], "construction_guidelines": [],
        "maintenance_components": [], "maintenance_services": [], "maintenance_defects": [],
        "ai_agents": [], "transactions": [], "rental_units": [], "products": [],
        "tools": [],
        "pmo_projects": [], "pmo_tasks": [], "pmo_risks": [],
        "msg_conversations": [], "msg_messages": [], "msg_actions": [],
    }
    for c in cities_db:
        if has(c.name, c.state, c.description):
            results["cities"].append({"id": c.id, "name": c.name, "state": c.state})
    for s in housing_schemes_db:
        if has(s.name, s.developer, s.description):
            results["schemes"].append({"id": s.id, "name": s.name, "city": city_name(s.city_id)})
    for b in block_zone_areas_db:
        if has(b.name, b.area_type):
            results["blocks"].append({"id": b.id, "name": b.name, "area_type": b.area_type})
    for p in properties_db:
        if has(p.title, p.description, p.category, p.use_type, p.sector, p.plot_number, p.street_address):
            results["properties"].append({"id": p.id, "title": p.title, "price": p.price,
                                          "category": p.category, "city": city_name(p.city_id)})
    for pr in big_projects_db:
        if has(pr.name, pr.project_type, pr.developer, pr.description):
            results["big_projects"].append({"id": pr.id, "name": pr.name, "type": pr.project_type})
    for poi in pois_db:
        if has(poi.name, poi.category, poi.subcategory, poi.address):
            results["pois"].append({"id": poi.id, "name": poi.name, "category": poi.category})
    for a in aois_db:
        if has(a.name, a.description, " ".join(a.tags)):
            results["areas_of_interest"].append({"id": a.id, "name": a.name, "kind": a.kind})
    for n in news_db:
        if has(n.title, n.summary, n.source, n.category):
            results["news"].append({"id": n.id, "title": n.title, "source": n.source})
    for a in agents_db:
        if has(a.name, a.email, a.region, a.specialization):
            results["agents"].append({"id": a.id, "name": a.name, "region": a.region})
    for l in leads_db:
        if has(l.name, l.email, l.phone, l.notes):
            results["leads"].append({"id": l.id, "name": l.name, "status": l.status})
    for c in customers_db:
        if has(c.name, c.email, c.phone, c.notes):
            results["customers"].append({"id": c.id, "name": c.name, "type": c.type})
    for d in deals_db:
        if has(d.title, d.stage):
            results["deals"].append({"id": d.id, "title": d.title, "amount": d.amount, "stage": d.stage})
    for pg in content.pages_db:
        if has(pg.key, pg.title, pg.summary, pg.subtitle, " ".join(pg.tags)):
            results["pages"].append({"key": pg.key, "title": pg.title, "category": pg.category})
    for ad in content.ads_db:
        if has(ad.title, ad.headline, ad.body, ad.advertiser, ad.category, " ".join(ad.keywords)):
            results["advertisements"].append({"id": ad.id, "title": ad.title,
                                              "category": ad.category, "slot": ad.slot})
    for s in construction.CONSTRUCTION_SYSTEMS:
        if has(s["name"], s["key"], s["category"], s["description"], " ".join(s["tags"])):
            results["construction_techniques"].append(
                {"key": s["key"], "name": s["name"], "category": s["category"]})
    for m in construction.MATERIALS:
        if has(m["name"], m["key"], m["category"], m["unit"]):
            results["construction_materials"].append(
                {"key": m["key"], "name": m["name"], "unit": m["unit"], "rate": m["unit_rate"]})
    for g in construction.CONSTRUCTION_GUIDELINES:
        if has(g["title"], g["category"], g["authority"], g["code"], g["summary"]):
            results["construction_guidelines"].append(
                {"key": g["key"], "title": g["title"], "category": g["category"]})
    for c in maintenance.ASSET_COMPONENTS:
        if has(c["name"], c["key"], c["category"]):
            results["maintenance_components"].append(
                {"key": c["key"], "name": c["name"], "category": c["category"]})
    for s in maintenance.MAINTENANCE_SERVICES:
        if has(s["name"], s["key"], s["category"], s["unit"]):
            results["maintenance_services"].append(
                {"key": s["key"], "name": s["name"], "unit": s["unit"]})
    for d in maintenance.DEFECT_CATALOGUE:
        if has(d["name"], d["key"], d["category"], " ".join(d["symptoms"]), " ".join(d["causes"])):
            results["maintenance_defects"].append(
                {"key": d["key"], "name": d["name"], "severity": d["severity"]})
    for ag in agents.AGENTS:
        if has(ag["key"], ag["name"], ag["category"], ag["summary"], ag["product"]):
            results["ai_agents"].append({"key": ag["key"], "name": ag["name"],
                                         "category": ag["category"], "autonomy": ag["autonomy"]})
    for tx in transactions.transactions_db:
        if has(tx.code, tx.property_title, tx.buyer_name, tx.seller_name, tx.transaction_type, tx.stage):
            results["transactions"].append({"id": tx.id, "code": tx.code, "stage": tx.stage,
                                            "price": tx.price, "title": tx.property_title})
    for u in leasing.units_db:
        if has(u.title, u.city, u.scheme, u.status):
            results["rental_units"].append({"id": u.id, "title": u.title, "rent": u.rent,
                                            "status": u.status})
    for pr in commercial.PRODUCTS:
        if has(pr["key"], pr["name"], pr["segment"], pr["positioning"], " ".join(pr["pricing_models"])):
            results["products"].append({"key": pr["key"], "name": pr["name"],
                                        "priority": pr["priority"], "segment": pr["segment"]})
    for tl in tools.TOOL_CATALOG:
        if has(tl["key"], tl["name"], tl["blurb"], tl["category"],
               tools.TOOL_CATEGORIES.get(tl["category"], "")):
            results["tools"].append({"key": tl["key"], "name": tl["name"],
                                     "category": tl["category"], "phase": tl["phase"],
                                     "tool": tl["mcp_tool"]})
    for pr in pmo.projects_db:
        if has(pr.code, pr.name, pr.project_type, pr.city, pr.scheme, pr.client, pr.status):
            results["pmo_projects"].append({"id": pr.id, "code": pr.code, "name": pr.name,
                                            "status": pr.status, "type": pr.project_type})
    for pt in pmo.tasks_db:
        if has(pt.name, pt.wbs, pt.phase_key):
            results["pmo_tasks"].append({"id": pt.id, "name": pt.name, "wbs": pt.wbs,
                                         "project_id": pt.project_id, "status": pt.status,
                                         "progress_pct": pt.progress_pct})
    for rk in pmo.risks_db:
        if has(rk.title, rk.kind, rk.category, rk.owner, rk.description):
            results["pmo_risks"].append({"id": rk.id, "title": rk.title, "kind": rk.kind,
                                         "score": rk.probability * rk.impact})
    for cv in messaging.conversations_db:
        if has(cv.title, cv.topic, cv.channel_key, cv.kind, cv.property_id):
            results["msg_conversations"].append({"id": cv.id, "title": cv.title, "kind": cv.kind,
                                                 "channel_key": cv.channel_key, "status": cv.status})
    for ms in messaging.messages_db:
        if ms.deleted_at:
            continue
        if has(ms.body, ms.author_name):
            results["msg_messages"].append({"id": ms.id, "conversation_id": ms.conversation_id,
                                            "author": ms.author_name, "body": ms.body[:160],
                                            "created_at": ms.created_at})
    for ac in messaging.actions_db:
        if has(ac.title, ac.detail, ac.kind, ac.status):
            results["msg_actions"].append({"id": ac.id, "title": ac.title, "kind": ac.kind,
                                           "status": ac.status, "owner_id": ac.owner_id,
                                           "conversation_id": ac.conversation_id})

    for key in results:
        results[key] = results[key][:limit]
    total = sum(len(v) for v in results.values())
    return dump({"query": query, "total": total, "results": results})


@mcp.tool()
def portal_statistics() -> str:
    """Portfolio-wide statistics: inventory, valuation, area, POIs and finance in one view."""
    metrics = _property_metrics(properties_db)
    by_city: Dict[str, Dict[str, Any]] = {}
    for p in properties_db:
        name = city_name(p.city_id)
        row = by_city.setdefault(name, {"city": name, "properties": 0, "value": 0.0})
        row["properties"] += 1
        row["value"] += p.price or 0.0
    for row in by_city.values():
        row["value"] = round(row["value"], 2)
    dash = accounting.accounting_dashboard()
    pipeline = round(sum(d.amount * (d.probability / 100.0) for d in deals_db), 2)
    return dump(
        {
            "inventory": {
                "cities": len(cities_db), "schemes": len(housing_schemes_db),
                "blocks": len(block_zone_areas_db), "properties": len(properties_db),
                "big_projects": len(big_projects_db), "pois": len(pois_db), "aois": len(aois_db),
            },
            "portfolio": {
                "total_market_value": metrics["total_market_value"],
                "avg_price": metrics["avg_price"],
                "median_price": metrics["median_price"],
                "price_per_marla": metrics["price_per_marla"],
                "built_sqft": metrics["built_sqft"],
                "land_sqft": metrics["land_sqft"],
                "by_category": metrics["by_category"],
                "by_use_type": metrics["by_use_type"],
                "by_city": sorted(by_city.values(), key=lambda r: -r["value"]),
            },
            "finance": {
                "total_assets": dash["total_assets"], "total_liabilities": dash["total_liabilities"],
                "total_equity": dash["total_equity"], "cash_and_bank": dash["cash_and_bank"],
                "accounts_receivable": dash["accounts_receivable"],
                "accounts_payable": dash["accounts_payable"],
                "revenue": dash["revenue"], "net_profit": dash["net_profit"],
                "overdue_invoices": dash["overdue_invoices"],
            },
            "crm": {
                "agents": len(agents_db), "leads": len(leads_db), "customers": len(customers_db),
                "deals": len(deals_db), "weighted_pipeline_value": pipeline,
            },
            "content": {
                "pages": len(content.pages_db), "history": len(content.history_db),
                "contacts": len(content.contacts_db), "success_stories": len(content.stories_db),
                "advertisements": len(content.ads_db),
                "live_advertisements": sum(1 for a in content.ads_db if content.is_live(a)),
            },
            "users_and_roles": {
                "users": len(auth.users_db),
                "roles": len(auth.roles_db),
                "permissions": len(auth.PERMISSIONS),
                "by_area": auth.role_summary()["by_area"],
            },
            "construction": {
                "techniques": len(construction.CONSTRUCTION_SYSTEMS),
                "materials": len(construction.MATERIALS),
                "element_rates": len(construction.ELEMENT_RATES),
                "guidelines": len(construction.CONSTRUCTION_GUIDELINES),
                "saved_estimates": len(construction.estimates_db),
                "building_types": sorted(construction.BUILDING_TYPES),
                "quality_tiers": sorted(construction.CONSTRUCTION_CONFIG["quality_base_rate_sqft"]),
            },
            "maintenance": {
                "components": len(maintenance.ASSET_COMPONENTS),
                "services": len(maintenance.MAINTENANCE_SERVICES),
                "defects": len(maintenance.DEFECT_CATALOGUE),
                "guidelines": len(maintenance.MAINTENANCE_GUIDELINES),
                "amc_tiers": sorted(maintenance.MAINTENANCE_TIERS),
                "saved_plans": len(maintenance.plans_db),
                "work_orders": len(maintenance.work_orders_db),
                "open_work_orders": sum(1 for w in maintenance.work_orders_db if w.status == "open"),
            },
            "agentic": agents.agentic_overview()["counts"],
            "transactions": {
                "total": len(transactions.transactions_db),
                "open": sum(1 for t in transactions.transactions_db if t.status == "open"),
                "closed": sum(1 for t in transactions.transactions_db if t.status == "closed"),
                "fallen_through": sum(1 for t in transactions.transactions_db
                                      if t.status == "fallen_through"),
                "gross_value_open": round(sum(t.price for t in transactions.transactions_db
                                              if t.status == "open"), 2),
                "offers": len(transactions.offers_db),
                "types": sorted(transactions.TRANSACTION_TYPES),
            },
            "leasing": {
                "units": len(leasing.units_db),
                "listed": sum(1 for u in leasing.units_db if u.status == "listed"),
                "let": sum(1 for u in leasing.units_db if u.status == "let"),
                "inquiries": len(leasing.inquiries_db),
                "auto_handled": sum(1 for i in leasing.inquiries_db if i.auto_handled),
                "applications": len(leasing.applications_db),
                "channels": leasing.LEASING_CONFIG["channels"],
            },
            "marketing": {
                "leads": len(marketing.leads_db),
                "routes": len(marketing.routes_db),
                "content_assets": len(marketing.assets_db),
                "campaigns": len(marketing.campaigns_db),
                "funnel": marketing.funnel_stats(),
            },
            "commercial": {
                "products": len(commercial.PRODUCTS),
                "plans": len(commercial.PLANS),
                "subscriptions": len(commercial.subscriptions_db),
                "meter_events": len(commercial.meter_events_db),
                "payouts": len(commercial.payouts_db),
                "pricing_models": sorted(commercial.PRICING_MODELS),
                "by_priority": {p: sum(1 for x in commercial.PRODUCTS if x["priority"] == p)
                                for p in ("P0", "P1", "P2")},
            },
            "tools": {
                "tools": len(tools.TOOL_CATALOG),
                "categories": len(tools.TOOL_CATEGORIES),
                "calculators": len(tools.calculator_catalog()["calculators"]),
                "crs_systems": len(tools.crs_catalog()["systems"]),
                "cad_formats": len(tools.CAD_FORMATS),
                "area_units": len(tools.AREA_UNITS),
                "saved_projects": len(tools.projects_db),
                "by_phase": tools.tools_overview()["by_phase"],
            },
            "pmo": {
                "projects": len(pmo.projects_db),
                "active": sum(1 for p in pmo.projects_db if p.status == "active"),
                "phases": len(pmo.phases_db), "milestones": len(pmo.milestones_db),
                "tasks": len(pmo.tasks_db), "resources": len(pmo.resources_db),
                "allocations": len(pmo.allocations_db),
                "cost_entries": len(pmo.cost_entries_db),
                "progress_updates": len(pmo.progress_updates_db),
                "risks": len(pmo.risks_db),
                "high_risks": sum(1 for r in pmo.risks_db if r.probability * r.impact >= 10),
                "site_logs": len(pmo.site_logs_db),
                "change_requests": len(pmo.change_requests_db),
                "inspections": len(pmo.inspections_db), "actions": len(pmo.actions_db),
                "by_health": pmo.portfolio_dashboard()["by_health"],
                "portfolio_spi": pmo.portfolio_dashboard()["portfolio_spi"],
                "portfolio_cpi": pmo.portfolio_dashboard()["portfolio_cpi"],
                "capabilities": len(pmo.PM_CAPABILITIES),
            },
            "messaging": messaging.messaging_statistics(),
        }
    )


@mcp.tool()
def property_availability(
    city: Optional[str] = None,
    scheme: Optional[str] = None,
    use_type: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
) -> str:
    """Availability breakdown of the listing book (by status / use / category) with the listings."""
    city_obj = resolve_city(city) if city else None
    scheme_obj = resolve_scheme(scheme) if scheme else None
    rows = list(properties_db)
    if city_obj:
        rows = [p for p in rows if p.city_id == city_obj.id]
    if scheme_obj:
        rows = [p for p in rows if p.scheme_id == scheme_obj.id]
    if use_type:
        rows = [p for p in rows if p.use_type == use_type]
    if category:
        rows = [p for p in rows if p.category == category]
    if status:
        rows = [p for p in rows if p.status == status]

    def tally(field: str) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for p in rows:
            key = str(getattr(p, field))
            out[key] = out.get(key, 0) + 1
        return out

    return dump(
        {
            "filters": {"city_id": city_obj.id if city_obj else None,
                        "scheme_id": scheme_obj.id if scheme_obj else None,
                        "use_type": use_type, "category": category, "status": status},
            "count": len(rows),
            "by_status": tally("status"),
            "by_use_type": tally("use_type"),
            "by_category": tally("category"),
            "total_value": round(sum(p.price or 0.0 for p in rows), 2),
            "listings": [
                {"id": p.id, "title": p.title, "price": p.price, "status": p.status,
                 "use_type": p.use_type, "category": p.category, "city": city_name(p.city_id)}
                for p in sorted(rows, key=lambda x: -(x.price or 0))[:limit]
            ],
        }
    )


@mcp.tool()
def market_trends(
    city: Optional[str] = None, scheme: Optional[str] = None, years: int = 5, days: int = 180
) -> str:
    """Market trends for a market: pricing, factor index, news momentum, forecast and yields."""
    city_obj = resolve_city(city) if city else None
    scheme_obj = resolve_scheme(scheme) if scheme else None
    props = list(properties_db)
    if city_obj:
        props = [p for p in props if p.city_id == city_obj.id]
    if scheme_obj:
        props = [p for p in props if p.scheme_id == scheme_obj.id]
    metrics = _property_metrics(props)
    scope_type, scope_id = (
        ("scheme", scheme_obj.id) if scheme_obj else ("city", city_obj.id) if city_obj else ("national", "PK")
    )
    scores = _factor_dict(_find_factor(scope_type, scope_id))
    index = _composite_index(scores)
    news_summary = _news_sentiment(
        city_id=city_obj.id if city_obj else None, scheme_id=scheme_obj.id if scheme_obj else None, days=days
    )
    analysis = _area_analysis(
        scheme_obj.name if scheme_obj else city_obj.name if city_obj else "Pakistan", props,
        geometry=_entity_geometry(scope_type, scope_id, props) if scope_type in ("city", "scheme") else None,
    )
    forecast = _forecast(analysis, scores, news_summary, years=years)
    roll = accounting.rent_roll()
    yield_pct = round(roll["annual_rent"] / metrics["total_market_value"], 4) if metrics["total_market_value"] else None
    return dump(
        {
            "scope": {"scope_type": scope_type, "scope_id": scope_id,
                      "city_id": city_obj.id if city_obj else None,
                      "scheme_id": scheme_obj.id if scheme_obj else None},
            "supply": {"listings": metrics["count"], "by_category": metrics["by_category"],
                       "by_use_type": metrics["by_use_type"]},
            "pricing": {"avg_price": metrics["avg_price"], "median_price": metrics["median_price"],
                        "price_per_marla": metrics["price_per_marla"],
                        "total_market_value": metrics["total_market_value"]},
            "factors": {"scores": scores, "index": index},
            "news": news_summary,
            "forecast": {"composite_index": forecast["composite_index"],
                         "index_band": forecast["index_band"], "base_cagr": forecast["base_cagr"],
                         "scenarios": forecast["scenarios"]},
            "yield": {"annual_rent": roll["annual_rent"], "blended_yield": yield_pct},
        }
    )


@mcp.resource("portal://health", name="Portal health", description="Liveness and store counts.")
def res_portal_health() -> str:
    return portal_health()


@mcp.resource("portal://catalog", name="Portal catalog", description="Every tool, resource and prompt.")
def res_portal_catalog() -> str:
    return portal_catalog()


@mcp.resource("portal://settings", name="Portal settings", description="Runtime assumptions and constants.")
def res_portal_settings() -> str:
    return portal_settings()


@mcp.resource("portal://statistics", name="Portal statistics", description="Portfolio-wide statistics.")
def res_portal_statistics() -> str:
    return portal_statistics()


@mcp.prompt(name="market_briefing_prompt", description="Prepare a market briefing for a city or scheme.")
def prompt_market_briefing(market: str = "Lahore") -> str:
    return (
        f"Prepare a market briefing for {market}.\n"
        "Use market_trends, news_list, news_impact, gis_market_factors, gis_forecast and "
        "portal_statistics. Cover supply, pricing, demand, infrastructure, regulatory and political "
        "drivers, then give a 2-page executive summary with a 12-month outlook."
    )


@mcp.prompt(name="data_onboarding_prompt", description="Onboard a new city / society into the portal.")
def prompt_data_onboarding(city: str = "") -> str:
    target = f" for {city}" if city else ""
    return (
        f"Onboard a new market{target} into the portal.\n"
        "1. add_city / add_scheme / add_block_zone_area to build the hierarchy.\n"
        "2. poi_add to register schools, hospitals, malls, transport and parks.\n"
        "3. aoi_create to save the key watch areas.\n"
        "4. gis_add_layer / gis_add_master_plan to attach the layout and master plan.\n"
        "5. news_add to seed the ticker, then portal_health to verify the counts."
    )


# ============================================================
# ============ PORTAL CONTENT & ADVERTISEMENTS ===============
# ============================================================


def _portal_ticker(lang: str = "en", limit: int = 14) -> str:
    """A news ticker fragment for the portal chrome."""
    items = sorted(news_db, key=lambda n: n.published_at, reverse=True)[:limit]
    if not items:
        return ""
    return gis.build_ticker_html([model_dict(n) for n in items], label="Real Estate News", lang=lang)


def _portal_stats_cards() -> List[Dict[str, Any]]:
    """Highlight cards used by the portal 'at a glance' section."""
    metrics = _property_metrics(properties_db)
    roll = accounting.rent_roll()
    return [
        {"label": "Live listings", "value": f"{len(properties_db):,}",
         "sub": f"{len(cities_db)} cities · {len(housing_schemes_db)} schemes"},
        {"label": "Big projects", "value": f"{len(big_projects_db):,}",
         "sub": "malls · towers · mixed-use · compounds"},
        {"label": "Points of interest", "value": f"{len(pois_db):,}",
         "sub": f"{len(aois_db)} saved areas of interest"},
        {"label": "Market value", "value": f"Rs {metrics['total_market_value']/1e9:,.2f}B",
         "sub": "portfolio valuation"},
        {"label": "Monthly rent roll", "value": f"Rs {roll['monthly_rent']/1e6:,.2f}M",
         "sub": f"{roll['leases']} active leases"},
        {"label": "Success stories", "value": f"{len(content.stories_db):,}",
         "sub": "client wins & case studies"},
        {"label": "Partners", "value": f"{len(content.ads_db):,}",
         "sub": "advertisers across the portal"},
        {"label": "Content pages", "value": f"{len(content.pages_db):,}",
         "sub": "about · services · help · policies"},
    ]


@mcp.tool()
def content_overview() -> str:
    """Counts and breakdowns for every content page, timeline entry, contact, story and ad."""
    return dump(content.content_overview())


# ---------- Content pages (mini-CMS) ----------


@mcp.tool()
def content_page_list(
    category: Optional[str] = None, tag: Optional[str] = None,
    status: str = "published", nav_only: bool = False,
) -> str:
    """List portal content pages (about, services, faq, policy …)."""
    rows = content.list_pages(category=category, status=status, tag=tag, nav_only=nav_only)
    return dump({"count": len(rows), "pages": [model_dict(p) for p in rows]})


@mcp.tool()
def content_page_get(key: str) -> str:
    """Fetch one content page by key (slug) or id."""
    page = content.find_page(key)
    if not page:
        return dump({"error": f"Page not found: {key}"})
    return dump(model_dict(page))


@mcp.tool()
def content_page_create(
    key: str,
    title: str,
    category: str = "about",
    subtitle: Optional[str] = None,
    summary: Optional[str] = None,
    body: Optional[List[str]] = None,
    highlights: Optional[List[Dict[str, str]]] = None,
    bullets: Optional[List[str]] = None,
    faqs: Optional[List[Dict[str, str]]] = None,
    tags: Optional[List[str]] = None,
    nav_label: Optional[str] = None,
    show_in_nav: bool = True,
    order: int = 100,
    status: str = "published",
) -> str:
    """Create a portal content page. ``highlights`` are ``{label,value,sub}`` cards,
    ``faqs`` are ``{question,answer}`` blocks."""
    if content.find_page(key):
        return dump({"error": f"A page with key '{key}' already exists"})
    page = content.PortalPage(
        key=key, title=title, category=category, subtitle=subtitle, summary=summary,
        body=body or [], highlights=highlights or [], bullets=bullets or [], faqs=faqs or [],
        tags=tags or [], nav_label=nav_label, show_in_nav=show_in_nav, order=order, status=status,
    )
    content.pages_db.append(page)
    return dump(model_dict(page))


@mcp.tool()
def content_page_update(
    key: str,
    title: Optional[str] = None,
    category: Optional[str] = None,
    subtitle: Optional[str] = None,
    summary: Optional[str] = None,
    body: Optional[List[str]] = None,
    highlights: Optional[List[Dict[str, str]]] = None,
    bullets: Optional[List[str]] = None,
    faqs: Optional[List[Dict[str, str]]] = None,
    tags: Optional[List[str]] = None,
    nav_label: Optional[str] = None,
    show_in_nav: Optional[bool] = None,
    order: Optional[int] = None,
    status: Optional[str] = None,
) -> str:
    """Update a portal content page."""
    page = content.find_page(key)
    if not page:
        return dump({"error": f"Page not found: {key}"})
    fields = {
        "title": title, "category": category, "subtitle": subtitle, "summary": summary,
        "body": body, "highlights": highlights, "bullets": bullets, "faqs": faqs, "tags": tags,
        "nav_label": nav_label, "show_in_nav": show_in_nav, "order": order, "status": status,
    }
    for name, value in fields.items():
        if value is not None:
            setattr(page, name, value)
    page.updated_at = datetime.now().isoformat(timespec="seconds")
    return dump(model_dict(page))


@mcp.tool()
def content_page_delete(key: str) -> str:
    """Delete a portal content page."""
    page = content.find_page(key)
    if not page:
        return dump({"error": f"Page not found: {key}"})
    content.pages_db.remove(page)
    return dump({"deleted": page.id, "key": page.key})


# ---------- History timeline ----------


@mcp.tool()
def content_history(
    kind: Optional[str] = None, since: Optional[int] = None,
    until: Optional[int] = None, featured: Optional[bool] = None,
) -> str:
    """The portal's company-history timeline, newest-facing, filterable by era and kind."""
    rows = content.list_history(kind=kind, since=since, until=until, featured=featured)
    return dump({
        "count": len(rows), "kinds": content.HISTORY_KINDS,
        "items": [model_dict(h) for h in rows],
    })


@mcp.tool()
def content_history_add(
    year: int,
    title: str,
    description: str,
    kind: str = "milestone",
    month: Optional[int] = None,
    tags: Optional[List[str]] = None,
    featured: bool = False,
) -> str:
    """Add an entry to the company-history timeline."""
    if kind not in content.HISTORY_KINDS:
        return dump({"error": f"kind must be one of {content.HISTORY_KINDS}"})
    entry = content.HistoryEntry(
        year=year, month=month, title=title, description=description, kind=kind,
        tags=tags or [], featured=featured,
    )
    content.history_db.append(entry)
    return dump(model_dict(entry))


# ---------- Contact directory ----------


@mcp.tool()
def content_contact(
    channel_type: Optional[str] = None, city: Optional[str] = None,
    scheme: Optional[str] = None, primary_only: bool = False,
) -> str:
    """The portal's contact directory: phone, e-mail, WhatsApp, offices, hours, social."""
    city_obj = resolve_city(city) if city else None
    scheme_obj = resolve_scheme(scheme) if scheme else None
    rows = content.list_contacts(
        channel_type=channel_type, city_id=city_obj.id if city_obj else None,
        scheme_id=scheme_obj.id if scheme_obj else None, primary_only=primary_only,
    )
    return dump({"count": len(rows), "types": content.CONTACT_TYPES,
                 "channels": [model_dict(c) for c in rows]})


@mcp.tool()
def content_contact_add(
    channel_type: str,
    label: str,
    value: str,
    url: Optional[str] = None,
    hours: Optional[str] = None,
    city: Optional[str] = None,
    scheme: Optional[str] = None,
    region: Optional[str] = None,
    priority: int = 100,
    is_primary: bool = False,
    notes: Optional[str] = None,
) -> str:
    """Add a contact channel (phone / email / whatsapp / office / hours / social / …)."""
    if channel_type not in content.CONTACT_TYPES:
        return dump({"error": f"channel_type must be one of {content.CONTACT_TYPES}"})
    city_obj = resolve_city(city) if city else None
    scheme_obj = resolve_scheme(scheme) if scheme else None
    channel = content.ContactChannel(
        channel_type=channel_type, label=label, value=value, url=url, hours=hours,
        city_id=city_obj.id if city_obj else None, scheme_id=scheme_obj.id if scheme_obj else None,
        region=region, priority=priority, is_primary=is_primary, notes=notes,
    )
    content.contacts_db.append(channel)
    return dump(model_dict(channel))


# ---------- Success stories ----------


@mcp.tool()
def content_success_stories(
    story_type: Optional[str] = None, city: Optional[str] = None, scheme: Optional[str] = None,
    featured: Optional[bool] = None, tag: Optional[str] = None,
) -> str:
    """Client success stories, case studies and testimonials."""
    city_obj = resolve_city(city) if city else None
    scheme_obj = resolve_scheme(scheme) if scheme else None
    rows = content.list_stories(
        story_type=story_type, city_id=city_obj.id if city_obj else None,
        scheme_id=scheme_obj.id if scheme_obj else None, featured=featured, tag=tag,
    )
    return dump({"count": len(rows), "types": content.STORY_TYPES,
                 "stories": [model_dict(s) for s in rows]})


@mcp.tool()
def content_success_story_add(
    title: str,
    story_type: str = "case_study",
    client_name: Optional[str] = None,
    client_role: Optional[str] = None,
    quote: Optional[str] = None,
    rating: Optional[float] = None,
    location: Optional[str] = None,
    city: Optional[str] = None,
    scheme: Optional[str] = None,
    property_id: Optional[str] = None,
    project_id: Optional[str] = None,
    narrative: Optional[List[str]] = None,
    metrics: Optional[List[Dict[str, str]]] = None,
    highlights: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    featured: bool = False,
    date: Optional[str] = None,
) -> str:
    """Publish a success story (case study / testimonial / investment / milestone)."""
    if story_type not in content.STORY_TYPES:
        return dump({"error": f"story_type must be one of {content.STORY_TYPES}"})
    city_obj = resolve_city(city) if city else None
    scheme_obj = resolve_scheme(scheme) if scheme else None
    story = content.SuccessStory(
        title=title, story_type=story_type, client_name=client_name, client_role=client_role,
        quote=quote, rating=rating, location=location,
        city_id=city_obj.id if city_obj else None, scheme_id=scheme_obj.id if scheme_obj else None,
        property_id=property_id, project_id=project_id, narrative=narrative or [],
        metrics=metrics or [], highlights=highlights or [], tags=tags or [],
        featured=featured, date=date,
    )
    content.stories_db.append(story)
    return dump(model_dict(story))


# ---------- Site assembly & portal page ----------


@mcp.tool()
def content_navigation() -> str:
    """The portal's navigation menu, derived from published nav-visible pages."""
    return dump({"items": content.navigation()})


@mcp.tool()
def content_site(lang: str = "en", city: Optional[str] = None, scheme: Optional[str] = None) -> str:
    """The complete portal site payload: nav, layout blocks, pages, history, contacts,
    stories and the advertisement sections already resolved for the requested scope."""
    city_obj = resolve_city(city) if city else None
    scheme_obj = resolve_scheme(scheme) if scheme else None
    site = content.build_site(lang=lang, city_id=city_obj.id if city_obj else None,
                              scheme_id=scheme_obj.id if scheme_obj else None)
    return dump(site)


@mcp.tool()
def content_portal_home(
    lang: str = "en", theme: str = "auto", city: Optional[str] = None,
    scheme: Optional[str] = None, include_ticker: bool = True, include_stats: bool = True,
) -> str:
    """Render the full public **portal home page** (HTML) — about, history, success
    stories and contact, decorated with advertisement sections — in either language
    and theme."""
    city_obj = resolve_city(city) if city else None
    scheme_obj = resolve_scheme(scheme) if scheme else None
    site = content.build_site(lang=lang, city_id=city_obj.id if city_obj else None,
                              scheme_id=scheme_obj.id if scheme_obj else None)
    ticker = _portal_ticker(lang) if include_ticker else ""
    return gis.build_portal_html(
        site, ticker_html=ticker, stats=_portal_stats_cards() if include_stats else None,
        lang=lang, theme=theme,
    )


# ---------- Advertising ----------


@mcp.tool()
def ad_categories() -> str:
    """Advertisement categories (smart technology, construction techniques, materials …)."""
    return dump({"count": len(content.AD_CATEGORIES), "categories": content.AD_CATEGORIES})


@mcp.tool()
def ad_slots() -> str:
    """Advertisement slots (hero, banner, sidebar, in-feed, footer, newsletter)."""
    return dump({"count": len(content.AD_SLOTS), "slots": content.AD_SLOTS})


@mcp.tool()
def ad_create(
    title: str,
    headline: str,
    advertiser: str = "",
    category: str = "services",
    slot: str = "infeed",
    body: Optional[str] = None,
    keywords: Optional[List[str]] = None,
    cta_label: Optional[str] = None,
    cta_url: Optional[str] = None,
    media_url: Optional[str] = None,
    image_url: Optional[str] = None,
    tags: Optional[List[str]] = None,
    contact: Optional[str] = None,
    phone: Optional[str] = None,
    price_text: Optional[str] = None,
    offer: Optional[str] = None,
    city: Optional[str] = None,
    scheme: Optional[str] = None,
    lang: Optional[str] = None,
    priority: int = 100,
    weight: float = 1.0,
    status: str = "active",
    valid_from: Optional[str] = None,
    valid_until: Optional[str] = None,
    budget: float = 0.0,
    pricing: str = "flat",
    rate: float = 0.0,
) -> str:
    """Create an advertisement creative (a sponsored card placed in a slot).

    ``pricing`` is ``flat`` (fixed fee), ``cpm`` (``rate`` PKR per 1,000 impressions) or
    ``cpc`` (``rate`` PKR per click); spend accrues as the app reports views and clicks
    and the ad pauses when it reaches ``budget``."""
    if pricing not in content.AD_PRICING:
        return dump({"error": f"pricing must be one of {list(content.AD_PRICING)}"})
    if category not in content.AD_CATEGORIES:
        return dump({"error": f"category must be one of {list(content.AD_CATEGORIES)}"})
    if slot not in content.AD_SLOTS:
        return dump({"error": f"slot must be one of {list(content.AD_SLOTS)}"})
    if status not in content.AD_STATUSES:
        return dump({"error": f"status must be one of {content.AD_STATUSES}"})
    city_obj = resolve_city(city) if city else None
    scheme_obj = resolve_scheme(scheme) if scheme else None
    ad = content.Advertisement(
        title=title, headline=headline, body=body, advertiser=advertiser, category=category,
        slot=slot, keywords=keywords or [], cta_label=cta_label, cta_url=cta_url,
        media_url=media_url, image_url=image_url, tags=tags or [], contact=contact, phone=phone,
        price_text=price_text, offer=offer, city_id=city_obj.id if city_obj else None,
        scheme_id=scheme_obj.id if scheme_obj else None, lang=lang, priority=priority,
        weight=weight, status=status, valid_from=valid_from, valid_until=valid_until, budget=budget,
        pricing=pricing, rate=max(0.0, rate),
    )
    content.ads_db.append(ad)
    return dump(content.ad_view(ad))


@mcp.tool()
def ad_list(
    category: Optional[str] = None, slot: Optional[str] = None, status: Optional[str] = None,
    advertiser: Optional[str] = None, tag: Optional[str] = None, limit: int = 100,
) -> str:
    """List advertisement creatives with their live status and performance counters."""
    rows = content.list_ads(category=category, slot=slot, status=status,
                            advertiser=advertiser, tag=tag)[:limit]
    return dump({"count": len(rows), "advertisements": [content.ad_view(a) for a in rows]})


@mcp.tool()
def ad_get(ad_id: str) -> str:
    """Fetch one advertisement by id."""
    ad = content.find_ad(ad_id)
    if not ad:
        return dump({"error": f"Advertisement not found: {ad_id}"})
    return dump(content.ad_view(ad))


@mcp.tool()
def ad_update(
    ad_id: str,
    title: Optional[str] = None,
    headline: Optional[str] = None,
    body: Optional[str] = None,
    advertiser: Optional[str] = None,
    category: Optional[str] = None,
    slot: Optional[str] = None,
    cta_label: Optional[str] = None,
    cta_url: Optional[str] = None,
    image_url: Optional[str] = None,
    contact: Optional[str] = None,
    phone: Optional[str] = None,
    price_text: Optional[str] = None,
    offer: Optional[str] = None,
    tags: Optional[List[str]] = None,
    lang: Optional[str] = None,
    priority: Optional[int] = None,
    weight: Optional[float] = None,
    status: Optional[str] = None,
    valid_from: Optional[str] = None,
    valid_until: Optional[str] = None,
    budget: Optional[float] = None,
    pricing: Optional[str] = None,
    rate: Optional[float] = None,
) -> str:
    """Update an advertisement creative (including pausing/resuming it)."""
    ad = content.find_ad(ad_id)
    if not ad:
        return dump({"error": f"Advertisement not found: {ad_id}"})
    if pricing is not None and pricing not in content.AD_PRICING:
        return dump({"error": f"pricing must be one of {list(content.AD_PRICING)}"})
    if category is not None and category not in content.AD_CATEGORIES:
        return dump({"error": f"category must be one of {list(content.AD_CATEGORIES)}"})
    if slot is not None and slot not in content.AD_SLOTS:
        return dump({"error": f"slot must be one of {list(content.AD_SLOTS)}"})
    if status is not None and status not in content.AD_STATUSES:
        return dump({"error": f"status must be one of {content.AD_STATUSES}"})
    fields = {
        "title": title, "headline": headline, "body": body, "advertiser": advertiser,
        "category": category, "slot": slot, "cta_label": cta_label, "cta_url": cta_url,
        "image_url": image_url, "contact": contact, "phone": phone, "price_text": price_text,
        "offer": offer, "tags": tags, "lang": lang, "priority": priority, "weight": weight,
        "status": status, "valid_from": valid_from, "valid_until": valid_until, "budget": budget,
        "pricing": pricing, "rate": max(0.0, rate) if rate is not None else None,
    }
    for name, value in fields.items():
        if value is not None:
            setattr(ad, name, value)
    return dump(content.ad_view(ad))


@mcp.tool()
def ad_delete(ad_id: str) -> str:
    """Delete an advertisement creative."""
    ad = content.find_ad(ad_id)
    if not ad:
        return dump({"error": f"Advertisement not found: {ad_id}"})
    content.ads_db.remove(ad)
    return dump({"deleted": ad.id, "title": ad.title})


@mcp.tool()
def ad_active(
    slot: Optional[str] = None, category: Optional[str] = None, city: Optional[str] = None,
    scheme: Optional[str] = None, lang: Optional[str] = None, limit: Optional[int] = None,
) -> str:
    """The live, in-window, on-target creatives for a slot — priority- and
    exposure-weighted, exactly as the portal would rotate them."""
    city_obj = resolve_city(city) if city else None
    scheme_obj = resolve_scheme(scheme) if scheme else None
    rows = content.active_ads(
        slot=slot, category=category, city_id=city_obj.id if city_obj else None,
        scheme_id=scheme_obj.id if scheme_obj else None, lang=lang, limit=limit,
    )
    return dump({"count": len(rows), "slot": slot, "category": category,
                 "advertisements": [content.ad_view(a) for a in rows]})


@mcp.tool()
def ad_track(ad_id: str, event: str = "impression", count: int = 1) -> str:
    """Record ``impression`` / ``click`` / ``spend`` events for an advertisement."""
    return dump(content.record_ad_event(ad_id, event=event, count=count))


@mcp.tool()
def ad_performance(ad_id: Optional[str] = None) -> str:
    """Impression / click / CTR / budget performance — one ad, or the whole book."""
    return dump(content.ad_performance(ad_id))


@mcp.tool()
def ad_section(
    slot: str = "infeed", category: Optional[str] = None, city: Optional[str] = None,
    scheme: Optional[str] = None, lang: Optional[str] = None, limit: Optional[int] = None,
    heading: Optional[str] = None,
) -> str:
    """Build one advertisement *section* (heading + resolved creatives) as data."""
    city_obj = resolve_city(city) if city else None
    scheme_obj = resolve_scheme(scheme) if scheme else None
    return dump(content.ad_section(slot=slot, category=category, city_id=city_obj.id if city_obj else None,
                                   scheme_id=scheme_obj.id if scheme_obj else None, lang=lang,
                                   limit=limit, heading=heading))


@mcp.tool()
def ad_preview(
    slot: str = "infeed", category: Optional[str] = None, lang: str = "en", theme: str = "auto",
    city: Optional[str] = None, scheme: Optional[str] = None, limit: Optional[int] = None,
) -> str:
    """Render one advertisement section as standalone, themed HTML."""
    city_obj = resolve_city(city) if city else None
    scheme_obj = resolve_scheme(scheme) if scheme else None
    section = content.ad_section(slot=slot, category=category, city_id=city_obj.id if city_obj else None,
                                 scheme_id=scheme_obj.id if scheme_obj else None, lang=lang, limit=limit)
    title = section.get("heading") or "Sponsored"
    return gis.build_report_html(
        title=f"{title} — Advertisement preview",
        subtitle=f"Slot: {section.get('slot_label', slot)}",
        sections=[section, {"kind": "kv", "heading": "Slot details",
                            "items": [["Slot", section.get("slot")],
                                      ["Category", section.get("category") or "all"],
                                      ["Live creatives", section.get("count")]]}],
        lang=lang, theme=theme,
    )


@mcp.tool()
def ad_report(lang: str = "en", theme: str = "auto") -> str:
    """Render a printable **advertising report**: every slot's live creatives plus
    delivery/CTR performance."""
    sections: List[Dict[str, Any]] = []
    for slot in content.AD_SLOTS:
        section = content.ad_section(slot=slot, lang=lang)
        if section["count"]:
            sections.append(section)
    perf = content.ad_performance()
    perf_rows = []
    for ad in sorted(content.ads_db, key=lambda x: -x.impressions):
        v = content.ad_view(ad)
        perf_rows.append([v["title"], v["category_label"], v["slot_label"],
                          v["impressions"], v["clicks"], f"{v['ctr']*100:.2f}%"])
    sections.append({
        "kind": "table", "heading": "Delivery performance",
        "columns": ["Ad", "Category", "Slot", "Impressions", "Clicks", "CTR"],
        "numeric": ["Impressions", "Clicks", "CTR"],
        "rows": perf_rows,
    })
    t = perf["totals"]
    sections.append({"kind": "cards", "heading": "Totals",
                     "items": [["Live ads", t["live"], f"of {t['ads']}"],
                               ["Impressions", f"{t['impressions']:,}", "all time"],
                               ["Clicks", f"{t['clicks']:,}", "all time"],
                               ["CTR", f"{t['ctr']*100:.2f}%", "blended"],
                               ["Spend", f"Rs {t['spend']:,.0f}", f"of Rs {t['budget']:,.0f}"]]})
    return gis.build_report_html(
        title="Advertising report", subtitle="Portal advertisement sections & delivery",
        sections=sections, ticker_html=_portal_ticker(lang), lang=lang, theme=theme,
    )


@mcp.resource("content://overview", name="Content overview", description="Counts and breakdowns for pages, history, contacts, stories and ads.")
def res_content_overview() -> str:
    return content_overview()


@mcp.resource("content://pages", name="Content pages", description="Every published portal page.")
def res_content_pages() -> str:
    return content_page_list()


@mcp.resource("content://page/{key}", name="Content page", description="One portal page by key.")
def res_content_page(key: str) -> str:
    return content_page_get(key)


@mcp.resource("content://history", name="Company history", description="Dated milestone timeline.")
def res_content_history() -> str:
    return content_history()


@mcp.resource("content://contacts", name="Contact directory", description="Phone / e-mail / office / hours / social channels.")
def res_content_contacts() -> str:
    return content_contact()


@mcp.resource("content://stories", name="Success stories", description="Case studies, testimonials and milestones.")
def res_content_stories() -> str:
    return content_success_stories()


@mcp.resource("content://site", name="Portal site", description="Full portal payload: nav, layout blocks, content and resolved ads.")
def res_content_site() -> str:
    return content_site()


@mcp.resource("content://portal-home", name="Portal home page", description="Rendered public portal home page (HTML).")
def res_content_home() -> str:
    return content_portal_home()


@mcp.resource("ads://categories", name="Ad categories", description="Advertisement categories (smart technology, materials …).")
def res_ads_categories() -> str:
    return ad_categories()


@mcp.resource("ads://slots", name="Ad slots", description="Advertisement slots (hero, banner, sidebar, in-feed, footer, newsletter).")
def res_ads_slots() -> str:
    return ad_slots()


@mcp.resource("ads://all", name="All advertisements", description="Every advertisement creative with performance counters.")
def res_ads_all() -> str:
    return ad_list()


@mcp.resource("ads://active", name="Live advertisements", description="Live, in-window, on-target creatives per slot.")
def res_ads_active() -> str:
    return ad_active()


@mcp.resource("ads://performance", name="Ad performance", description="Impression / click / CTR performance for the whole book.")
def res_ads_performance() -> str:
    return ad_performance()


@mcp.resource("routes://config", name="Routing config", description="Travel modes, road classes and routing assumptions.")
def res_routes_config() -> str:
    return dump({"modes": gis.travel_modes(), "road_classes": gis.road_classes(),
                 "config": gis.ROUTE_CONFIG, "networks": [n.info() for n in road_networks_db.values()]})


@mcp.resource("roles://all", name="Roles", description="Every portal role with its permission list.")
def res_roles_all() -> str:
    return auth_list_roles()


@mcp.resource("roles://role/{name}", name="Role", description="One role by name.")
def res_roles_one(name: str) -> str:
    return auth_get_role(name)


@mcp.resource("roles://permissions", name="Permission catalogue", description="The full permission catalogue (resource.action).")
def res_roles_permissions() -> str:
    return auth_permissions()


@mcp.resource("roles://summary", name="Role summary", description="Roles by portal area and per-role member counts.")
def res_roles_summary() -> str:
    return auth_role_summary()


@mcp.resource("roles://user/{user_id}", name="User roles", description="Effective roles and permissions of a user.")
def res_roles_user(user_id: str) -> str:
    return auth_user_permissions(user_id=user_id)


@mcp.prompt(name="content_review_prompt", description="Review the portal's editorial content and ads.")
def prompt_content_review(lang: str = "en") -> str:
    return (
        "You are the managing editor of a Pakistani real-estate portal.\n"
        f"Read the portal content with content_site (lang={lang}) and content_overview.\n"
        "1. Summarise the editorial sections (about, mission, services, why-us, FAQ, policies).\n"
        "2. Review the company history timeline for gaps or weak milestones.\n"
        "3. List the advertisement sections and note any slot that is under-filled.\n"
        "4. Recommend 3 concrete content or creative improvements, in priority order."
    )


@mcp.prompt(name="ad_campaign_prompt", description="Plan and place an advertising campaign.")
def prompt_ad_campaign(advertiser: str, category: str = "smart_technology", budget: str = "500000") -> str:
    return (
        "You are an advertising manager for a real-estate portal with slots: "
        "hero, banner, sidebar, infeed, footer, newsletter.\n"
        f"Advertiser: {advertiser}. Category: {category}. Budget: PKR {budget}.\n"
        "1. Use ad_slots and ad_categories to pick the best-matching slots.\n"
        "2. Draft 2–3 creative variants (headline, body, CTA, price/offer) with ad_create.\n"
        "3. Set priority/weight and a scheduling window.\n"
        "4. Explain the targeting (city / scheme / language) and how you will track CTR."
    )


@mcp.prompt(name="route_planning_prompt", description="Plan travel between two points by foot or car.")
def prompt_route_planning(origin: str, destination: str, mode: str = "drive") -> str:
    return (
        "You are a location analyst for a Pakistani property portal.\n"
        f"Origin: {origin}. Destination: {destination}. Preferred mode: {mode}.\n"
        "1. Use gis_route to compute the best route and its alternatives.\n"
        "2. Use gis_route_compare to compare on foot, bicycle and motor car (distance, time).\n"
        "3. Note which road classes dominate the chosen route.\n"
        "4. Recommend the best mode and route, and flag any long detours."
    )


@mcp.prompt(name="role_assignment_prompt", description="Design roles and permissions for a portal team.")
def prompt_role_assignment(persona: str = "sales agent") -> str:
    return (
        "You are an access-control administrator for a real-estate portal.\n"
        f"Persona to onboard: {persona}.\n"
        "1. Review available roles with auth_list_roles and the permission catalogue.\n"
        "2. Recommend the least-privilege role set for this persona (justify each permission).\n"
        "3. Show how to apply it with auth_set_user_roles, and how to verify with "
        "auth_check_permission and auth_user_permissions.\n"
        "4. Note any separation-of-duties conflicts to avoid."
    )


# ============================================================
# ============ ACCOUNTING & FINANCE (double entry) ===========
# ============================================================


@mcp.tool()
def accounting_info() -> str:
    """Accounting configuration, allowed values and live record counts."""
    return dump(accounting.accounting_info())


@mcp.tool()
def accounting_chart_of_accounts(
    account_type: Optional[str] = None,
    subtype: Optional[str] = None,
    active_only: bool = False,
) -> str:
    """The chart of accounts with live balances (filter by type / subtype)."""
    rows = accounting.list_accounts(type=account_type, subtype=subtype, active_only=active_only)
    return dump({"count": len(rows), "accounts": rows})


@mcp.tool()
def accounting_create_account(
    code: str,
    name: str,
    account_type: str = "asset",
    subtype: Optional[str] = None,
    parent_code: Optional[str] = None,
    normal_side: Optional[str] = None,
    description: Optional[str] = None,
    opening_balance: float = 0.0,
) -> str:
    """Add a ledger account. ``code`` is the primary key; ``account_type`` is
    asset / liability / equity / income / expense."""
    return dump(
        accounting.create_account(
            code=code, name=name, type=account_type, subtype=subtype, parent_code=parent_code,
            normal_side=normal_side, description=description, opening_balance=opening_balance,
        )
    )


@mcp.tool()
def accounting_update_account(
    code: str,
    name: Optional[str] = None,
    subtype: Optional[str] = None,
    description: Optional[str] = None,
    active: Optional[bool] = None,
) -> str:
    """Rename / reclassify / deactivate a ledger account."""
    return dump(
        accounting.update_account(code, name=name, subtype=subtype, description=description, active=active)
    )


@mcp.tool()
def accounting_account_balance(code: str, as_of: Optional[str] = None) -> str:
    """Debit/credit movement and the signed balance of a single account."""
    return dump(accounting.account_balance(code, as_of))


@mcp.tool()
def accounting_journal_post(
    lines: List[Dict[str, Any]],
    date: Optional[str] = None,
    memo: Optional[str] = None,
    reference: Optional[str] = None,
    created_by: Optional[str] = None,
) -> str:
    """Post a balanced double-entry journal entry.

    Each line is ``{account, debit, credit, description?, property_id?, scheme_id?, city_id?}``;
    total debits must equal total credits or the entry is rejected.
    """
    return dump(
        accounting.post_journal_entry(
            lines=lines, date=date, memo=memo, reference=reference, created_by=created_by
        )
    )


@mcp.tool()
def accounting_journal_list(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    source: Optional[str] = None,
    account: Optional[str] = None,
    property_id: Optional[str] = None,
    limit: int = 50,
) -> str:
    """Recent journal entries, filtered by date / source / account / property."""
    rows = accounting.list_journal_entries(
        from_date=from_date, to_date=to_date, source=source, account=account,
        property_id=property_id, limit=limit,
    )
    return dump({"count": len(rows), "entries": rows})


@mcp.tool()
def accounting_journal_get(entry_id: str) -> str:
    """Fetch one journal entry with its lines and totals."""
    return dump(accounting.get_journal_entry(entry_id))


@mcp.tool()
def accounting_journal_void(entry_id: str, reason: Optional[str] = None) -> str:
    """Void a journal entry (kept in the audit trail, removed from the statements)."""
    return dump(accounting.void_journal_entry(entry_id, reason))


@mcp.tool()
def accounting_trial_balance(as_of: Optional[str] = None) -> str:
    """Trial balance — debit/credit column per account, with a balanced check."""
    return dump(accounting.trial_balance(as_of))


@mcp.tool()
def accounting_general_ledger(
    account_code: str, from_date: Optional[str] = None, to_date: Optional[str] = None
) -> str:
    """Chronological postings for one account with a running balance."""
    return dump(accounting.general_ledger(account_code, from_date, to_date))


@mcp.tool()
def accounting_profit_and_loss(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    property_id: Optional[str] = None,
    scheme_id: Optional[str] = None,
    city_id: Optional[str] = None,
) -> str:
    """Profit & loss for a period, optionally scoped to a property / scheme / city."""
    return dump(
        accounting.profit_and_loss(
            from_date, to_date, property_id=property_id, scheme_id=scheme_id, city_id=city_id
        )
    )


@mcp.tool()
def accounting_balance_sheet(as_of: Optional[str] = None) -> str:
    """Assets, liabilities and equity at a point in time."""
    return dump(accounting.balance_sheet(as_of))


@mcp.tool()
def accounting_cash_flow(from_date: Optional[str] = None, to_date: Optional[str] = None) -> str:
    """Operating / investing / financing cash-flow statement."""
    return dump(accounting.cash_flow_statement(from_date, to_date))


@mcp.tool()
def accounting_ratios(as_of: Optional[str] = None) -> str:
    """Liquidity, leverage and profitability ratios (current, quick, D/E, ROE, ROA, margin)."""
    return dump(accounting.financial_ratios(as_of))


@mcp.tool()
def accounting_dashboard(as_of: Optional[str] = None) -> str:
    """Finance dashboard: assets, cash, AR/AP, revenue, profit, overdue and ratios."""
    return dump(accounting.accounting_dashboard(as_of))


@mcp.tool()
def accounting_invoice_create(
    counterparty: str,
    lines: List[Dict[str, Any]],
    invoice_type: str = "receivable",
    issue_date: Optional[str] = None,
    due_date: Optional[str] = None,
    tax_rate: Optional[float] = None,
    property_id: Optional[str] = None,
    scheme_id: Optional[str] = None,
    city_id: Optional[str] = None,
    lease_id: Optional[str] = None,
    notes: Optional[str] = None,
    auto_post: bool = False,
) -> str:
    """Create a receivable (we bill) or payable (we are billed) invoice with tax.

    ``lines`` is ``[{description, quantity?, unit_price?, amount?, tax_rate?}]``.
    """
    return dump(
        accounting.create_invoice(
            counterparty=counterparty, lines=lines, invoice_type=invoice_type, issue_date=issue_date,
            due_date=due_date, tax_rate=tax_rate, property_id=property_id, scheme_id=scheme_id,
            city_id=city_id, lease_id=lease_id, notes=notes, auto_post=auto_post,
        )
    )


@mcp.tool()
def accounting_invoice_list(
    invoice_type: Optional[str] = None,
    status: Optional[str] = None,
    counterparty: Optional[str] = None,
    property_id: Optional[str] = None,
    overdue_only: bool = False,
    limit: int = 50,
) -> str:
    """List invoices with balances and overdue flags."""
    rows = accounting.list_invoices(
        invoice_type=invoice_type, status=status, counterparty=counterparty,
        property_id=property_id, overdue_only=overdue_only, limit=limit,
    )
    return dump({"count": len(rows), "invoices": rows})


@mcp.tool()
def accounting_invoice_get(invoice_id: str) -> str:
    """One invoice (by id or number) with its payments."""
    return dump(accounting.get_invoice(invoice_id))


@mcp.tool()
def accounting_invoice_post(invoice_id: str) -> str:
    """Post an invoice to the ledger (AR/AP + income/expense + tax)."""
    return dump(accounting.post_invoice(invoice_id))


@mcp.tool()
def accounting_payment_record(
    amount: float,
    invoice_id: Optional[str] = None,
    direction: str = "in",
    method: str = "bank_transfer",
    account_code: str = accounting.ACC_BANK,
    date: Optional[str] = None,
    counterparty: Optional[str] = None,
    reference: Optional[str] = None,
    notes: Optional[str] = None,
) -> str:
    """Record a receipt (``in``) or disbursement (``out``) and allocate it to an invoice."""
    return dump(
        accounting.record_payment(
            amount=amount, invoice_id=invoice_id, direction=direction, method=method,
            account_code=account_code, date=date, counterparty=counterparty,
            reference=reference, notes=notes,
        )
    )


@mcp.tool()
def accounting_expense_create(
    amount: float,
    account_code: str = "5900",
    category: str = "misc",
    date: Optional[str] = None,
    vendor: Optional[str] = None,
    description: Optional[str] = None,
    tax_amount: float = 0.0,
    paid: bool = True,
    property_id: Optional[str] = None,
    scheme_id: Optional[str] = None,
    city_id: Optional[str] = None,
) -> str:
    """Capture an expense (posted to the ledger automatically)."""
    return dump(
        accounting.create_expense(
            amount=amount, account_code=account_code, category=category, date=date, vendor=vendor,
            description=description, tax_amount=tax_amount, paid=paid, property_id=property_id,
            scheme_id=scheme_id, city_id=city_id,
        )
    )


@mcp.tool()
def accounting_invoice_aging(as_of: Optional[str] = None, invoice_type: Optional[str] = None) -> str:
    """Receivable/payable ageing buckets (current, 1-30, 31-60, 61-90, 90+)."""
    return dump(accounting.invoice_aging(as_of, invoice_type))


@mcp.tool()
def accounting_lease_create(
    tenant: str,
    rent_amount: float,
    property_id: Optional[str] = None,
    unit_label: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    billing_cycle: str = "monthly",
    escalation_rate: Optional[float] = None,
    security_deposit: float = 0.0,
    tenant_id: Optional[str] = None,
    city_id: Optional[str] = None,
    scheme_id: Optional[str] = None,
    notes: Optional[str] = None,
) -> str:
    """Create a lease — it drives the rent roll and automatic rent invoices."""
    return dump(
        accounting.create_lease(
            tenant=tenant, rent_amount=rent_amount, property_id=property_id, unit_label=unit_label,
            start_date=start_date, end_date=end_date, billing_cycle=billing_cycle,
            escalation_rate=escalation_rate, security_deposit=security_deposit, tenant_id=tenant_id,
            city_id=city_id, scheme_id=scheme_id, notes=notes,
        )
    )


@mcp.tool()
def accounting_lease_list(
    status: Optional[str] = None,
    property_id: Optional[str] = None,
    scheme_id: Optional[str] = None,
    city_id: Optional[str] = None,
) -> str:
    """List leases with their monthly and annual rent."""
    rows = accounting.list_leases(status=status, property_id=property_id, scheme_id=scheme_id, city_id=city_id)
    return dump({"count": len(rows), "leases": rows})


@mcp.tool()
def accounting_rent_roll(as_of: Optional[str] = None) -> str:
    """Active leases, contracted rent and deposits held."""
    return dump(accounting.rent_roll(as_of))


@mcp.tool()
def accounting_generate_rent_invoices(
    period_month: Optional[int] = None, year: Optional[int] = None, auto_post: bool = True
) -> str:
    """Raise this period's rent invoices for every due lease (idempotent per month)."""
    return dump(accounting.generate_rent_invoices(period_month=period_month, year=year, auto_post=auto_post))


@mcp.tool()
def accounting_budget_create(
    name: str,
    lines: Dict[str, float],
    fiscal_year: str = "",
    scope: str = "portfolio",
    scope_id: Optional[str] = None,
    notes: Optional[str] = None,
) -> str:
    """Create a budget (``account_code -> amount``) for a fiscal year and scope."""
    return dump(
        accounting.create_budget(name, lines, fiscal_year=fiscal_year, scope=scope,
                                 scope_id=scope_id, notes=notes)
    )


@mcp.tool()
def accounting_budget_list() -> str:
    """List every budget."""
    rows = accounting.list_budgets()
    return dump({"count": len(rows), "budgets": rows})


@mcp.tool()
def accounting_budget_variance(budget_id: str) -> str:
    """Budget vs actual variance with favourable/unfavourable flags."""
    return dump(accounting.budget_variance(budget_id))


@mcp.tool()
def accounting_property_performance(
    property_id: str, from_date: Optional[str] = None, to_date: Optional[str] = None
) -> str:
    """Property-level P&L plus its rent roll, yields and net operating income."""
    p = find_property(property_id)
    if not p:
        return dump({"error": f"Property not found: {property_id}"})
    pl = accounting.profit_and_loss(from_date, to_date, property_id=property_id)
    leases = accounting.list_leases(property_id=property_id)
    annual_rent = round(sum(l["annual_rent"] for l in leases), 2)
    noi = round(annual_rent - pl["total_expenses"], 2)
    return dump(
        {
            "property": {"id": p.id, "title": p.title, "price": p.price,
                         "category": p.category, "use_type": p.use_type},
            "profit_and_loss": pl,
            "leases": leases,
            "annual_rent": annual_rent,
            "net_operating_income": noi,
            "gross_yield": round(annual_rent / p.price, 4) if p.price else None,
            "net_yield": round(noi / p.price, 4) if p.price else None,
        }
    )


# ---------- Finance / investment maths (ROI) ----------


@mcp.tool()
def finance_mortgage_calculator(
    principal: float,
    annual_rate: Optional[float] = None,
    years: Optional[int] = None,
    payments_per_year: int = 12,
) -> str:
    """Amortising mortgage: periodic payment, total interest and the full schedule."""
    return dump(
        accounting.mortgage_schedule(
            principal, annual_rate=annual_rate, years=years, payments_per_year=payments_per_year
        )
    )


@mcp.tool()
def finance_investment_metrics(cashflows: List[float], discount_rate: Optional[float] = None) -> str:
    """NPV, IRR, payback, discounted payback, profitability index, equity multiple and ROI
    for a cash-flow series (``cashflows[0]`` is normally the negative investment)."""
    return dump(accounting.investment_metrics(cashflows, discount_rate))


@mcp.tool()
def finance_cap_rate(noi: float, value: float) -> str:
    """Capitalisation rate and value multiple from net operating income and value."""
    return dump(accounting.cap_rate(noi, value))


@mcp.tool()
def finance_cash_on_cash(annual_cash_flow: float, cash_invested: float) -> str:
    """Cash-on-cash return (annual pre-tax cash flow ÷ cash invested)."""
    return dump(accounting.cash_on_cash(annual_cash_flow, cash_invested))


@mcp.tool()
def finance_roi_analysis(
    initial_investment: float,
    annual_cash_flow: float = 0.0,
    hold_years: Optional[int] = None,
    terminal_value: float = 0.0,
    discount_rate: Optional[float] = None,
    annual_growth: float = 0.0,
    annual_cost_inflation: float = 0.0,
    loan_amount: float = 0.0,
    loan_rate: Optional[float] = None,
    loan_years: Optional[int] = None,
) -> str:
    """Leveraged ROI analysis with pessimistic / base / optimistic scenarios."""
    return dump(
        accounting.roi_analysis(
            initial_investment=initial_investment, annual_cash_flow=annual_cash_flow,
            hold_years=hold_years, terminal_value=terminal_value, discount_rate=discount_rate,
            annual_growth=annual_growth, annual_cost_inflation=annual_cost_inflation,
            loan_amount=loan_amount, loan_rate=loan_rate, loan_years=loan_years,
        )
    )


@mcp.tool()
def finance_property_roi(
    purchase_price: float,
    annual_rent: float = 0.0,
    annual_expenses: float = 0.0,
    hold_years: Optional[int] = None,
    appreciation_rate: float = 0.075,
    discount_rate: Optional[float] = None,
    down_payment_share: float = 1.0,
    loan_rate: Optional[float] = None,
    loan_years: Optional[int] = None,
    selling_cost_rate: float = 0.02,
) -> str:
    """Property ROI: gross/net rental yield, appreciation, leverage, IRR and exit proceeds."""
    return dump(
        accounting.property_roi(
            purchase_price=purchase_price, annual_rent=annual_rent, annual_expenses=annual_expenses,
            hold_years=hold_years, appreciation_rate=appreciation_rate, discount_rate=discount_rate,
            down_payment_share=down_payment_share, loan_rate=loan_rate, loan_years=loan_years,
            selling_cost_rate=selling_cost_rate,
        )
    )


@mcp.tool()
def finance_rental_yield(
    property_id: str, annual_rent: Optional[float] = None, annual_expenses: float = 0.0
) -> str:
    """Gross/net rental yield and cap rate for a property (uses its lease rent when omitted)."""
    p = find_property(property_id)
    if not p:
        return dump({"error": f"Property not found: {property_id}"})
    leases = accounting.list_leases(property_id=property_id)
    rent = annual_rent if annual_rent is not None else round(sum(l["annual_rent"] for l in leases), 2)
    noi = round(rent - annual_expenses, 2)
    return dump(
        {
            "property_id": p.id, "title": p.title, "price": p.price,
            "annual_rent": rent, "annual_expenses": annual_expenses, "net_operating_income": noi,
            "gross_yield": round(rent / p.price, 4) if p.price else None,
            "net_yield": round(noi / p.price, 4) if p.price else None,
            "cap_rate": accounting.cap_rate(noi, p.price),
        }
    )


@mcp.tool()
def finance_portfolio_roi(
    discount_rate: Optional[float] = None,
    hold_years: int = 5,
    appreciation_rate: float = 0.075,
    city: Optional[str] = None,
    scheme: Optional[str] = None,
) -> str:
    """Portfolio ROI: aggregates the listed properties, the rent roll and the accounting
    position into a single leveraged ROI with scenarios."""
    city_obj = resolve_city(city) if city else None
    scheme_obj = resolve_scheme(scheme) if scheme else None
    props = list(properties_db)
    if city_obj:
        props = [p for p in props if p.city_id == city_obj.id]
    if scheme_obj:
        props = [p for p in props if p.scheme_id == scheme_obj.id]
    value = round(sum(p.price or 0.0 for p in props), 2)
    roll = accounting.rent_roll()
    monthly = roll["monthly_rent"]
    if scheme_obj:
        scoped = accounting.list_leases(scheme_id=scheme_obj.id)
        monthly = round(sum(l["monthly_rent"] for l in scoped), 2)
    elif city_obj:
        scoped = accounting.list_leases(city_id=city_obj.id)
        monthly = round(sum(l["monthly_rent"] for l in scoped), 2)
    annual_rent = round(monthly * 12, 2)
    pl = accounting.profit_and_loss(
        property_id=None, scheme_id=scheme_obj.id if scheme_obj else None,
        city_id=city_obj.id if city_obj else None,
    )
    noi = round(annual_rent - pl["total_expenses"], 2)
    terminal = round(value * ((1 + appreciation_rate) ** hold_years) * 0.98, 2)
    roi = accounting.roi_analysis(
        initial_investment=value or 1.0, annual_cash_flow=noi, hold_years=hold_years,
        terminal_value=terminal, discount_rate=discount_rate,
    )
    return dump(
        {
            "scope": {"city_id": city_obj.id if city_obj else None,
                      "scheme_id": scheme_obj.id if scheme_obj else None},
            "properties": len(props),
            "market_value": value,
            "annual_rent": annual_rent,
            "annual_expenses": pl["total_expenses"],
            "net_operating_income": noi,
            "gross_yield": round(annual_rent / value, 4) if value else None,
            "net_yield": round(noi / value, 4) if value else None,
            "cash_flow_statement": accounting.cash_flow_statement(),
            "roi": roi,
        }
    )


@mcp.resource("accounting://config", name="Accounting config", description="Accounting configuration and counters.")
def res_accounting_config() -> str:
    return accounting_info()


@mcp.resource("accounting://chart-of-accounts", name="Chart of accounts", description="Ledger accounts with balances.")
def res_accounting_coa() -> str:
    return accounting_chart_of_accounts()


@mcp.resource("accounting://trial-balance", name="Trial balance", description="Trial balance at today's date.")
def res_accounting_tb() -> str:
    return accounting_trial_balance()


@mcp.resource("accounting://dashboard", name="Finance dashboard", description="Accounting dashboard snapshot.")
def res_accounting_dashboard() -> str:
    return accounting_dashboard()


@mcp.resource("accounting://invoices", name="Invoices", description="All receivable and payable invoices.")
def res_accounting_invoices() -> str:
    return accounting_invoice_list(limit=200)


@mcp.resource("accounting://rent-roll", name="Rent roll", description="Active leases and contracted rent.")
def res_accounting_rentroll() -> str:
    return accounting_rent_roll()


@mcp.prompt(name="financial_review_prompt", description="Produce a financial review of the portfolio.")
def prompt_financial_review(period: str = "current fiscal year") -> str:
    return (
        "Act as a real-estate CFO.\n"
        f"Review the books for the {period}.\n"
        "1. Call accounting_dashboard and accounting_ratios.\n"
        "2. Call accounting_profit_and_loss, accounting_balance_sheet and accounting_cash_flow.\n"
        "3. Call accounting_rent_roll and accounting_invoice_aging.\n"
        "Summarise profitability, liquidity, leverage, arrears and cash conversion, then list the "
        "three most important corrective actions."
    )


@mcp.prompt(name="roi_review_prompt", description="Evaluate the ROI of a property or development deal.")
def prompt_roi_review(property_id: str = "", hold_years: int = 5) -> str:
    target = f"property {property_id}" if property_id else "the portfolio"
    return (
        "Act as a property investment analyst.\n"
        f"Evaluate {target} over a {hold_years}-year hold.\n"
        "Use finance_rental_yield, finance_property_roi, finance_mortgage_calculator and "
        "finance_investment_metrics, plus gis_cost_development_analysis for the development case.\n"
        "Report gross/net yield, cap rate, IRR, NPV, payback, equity multiple and the breakdown of "
        "value creation (income vs appreciation vs leverage), then give a buy/hold/pass verdict."
    )


# ============================================================
# ==================== SEED DATA =============================
# ============================================================


def _seed_accounting() -> None:
    """Populate the accounting module with a realistic ~14-month book."""
    accounting.seed_chart_of_accounts()

    def months_back(n: int) -> str:
        today = datetime.now().date()
        y, m = today.year, today.month
        for _ in range(n):
            m -= 1
            if m == 0:
                m = 12
                y -= 1
        return f"{y:04d}-{m:02d}-01"

    lsc = resolve_scheme("Lahore Smart City")
    gulberg = resolve_scheme("Gulberg Greens")
    lsc_id = lsc.id if lsc else None
    gulberg_id = gulberg.id if gulberg else None

    def _prop(title: str) -> Optional[Property]:
        return next((p for p in properties_db if p.title == title), None)

    def plus_years(stamp: str, years: int) -> str:
        return f"{int(stamp[:4]) + years:04d}{stamp[4:]}"

    shop = _prop("Ground Floor Commercial Shop")
    office = _prop("3,000 sqft Corporate Office")
    gfloor = _prop("Gulberg Office Floor")
    apartment_block = _prop("Employee Apartment Building")

    # ---- Opening capital ----
    accounting.post_journal_entry(
        [{"account": "1010", "debit": 150_000_000, "description": "Share capital"},
         {"account": "3000", "credit": 150_000_000}],
        date=months_back(14), memo="Opening share capital", source="opening", reference="OPEN-1",
    )

    # ---- Acquire land + buildings (investing) ----
    accounting.post_journal_entry(
        [{"account": "1300", "debit": 75_000_000, "description": "Buildings & improvements"},
         {"account": "1200", "debit": 45_000_000, "description": "Land & plots"},
         {"account": "1010", "credit": 120_000_000, "description": "Acquisition payment"}],
        date=months_back(13), memo="Acquire commercial portfolio", source="opening", reference="PUR-1",
    )

    # ---- Bank financing ----
    accounting.post_journal_entry(
        [{"account": "1010", "debit": 50_000_000, "description": "Term loan drawdown"},
         {"account": "2200", "credit": 50_000_000, "description": "Long-term bank loan"}],
        date=months_back(12), memo="Term loan drawdown", source="manual", reference="LOAN-1",
    )

    # ---- Leases ----
    if shop:
        accounting.create_lease(tenant="Metro Mart (Pvt) Ltd", rent_amount=250_000, property_id=shop.id,
                                unit_label="Shop G-01", start_date=months_back(14),
                                end_date=plus_years(months_back(14), 5), billing_cycle="monthly",
                                security_deposit=500_000, scheme_id=lsc_id, status="active")
    if office:
        accounting.create_lease(tenant="Nexus Technologies", rent_amount=1_800_000, property_id=office.id,
                                unit_label="Floor 5", start_date=months_back(14),
                                end_date=plus_years(months_back(14), 5), billing_cycle="quarterly",
                                security_deposit=3_600_000, status="active")
    if gfloor:
        accounting.create_lease(tenant="Hilltop Foods", rent_amount=450_000, property_id=gfloor.id,
                                unit_label="Executive Floor", start_date=months_back(14),
                                end_date=plus_years(months_back(14), 5),
                                billing_cycle="monthly", security_deposit=900_000,
                                scheme_id=gulberg_id, status="active")
    if apartment_block:
        accounting.create_lease(tenant="Zenith Residences", rent_amount=1_400_000, property_id=apartment_block.id,
                                unit_label="Whole building", start_date=months_back(14),
                                end_date=plus_years(months_back(14), 5),
                                billing_cycle="monthly", security_deposit=2_000_000, status="active")

    # ---- Rent invoices for the last 7 months ----
    for i in range(7, 0, -1):
        stamp = months_back(i)
        year, month = int(stamp[:4]), int(stamp[5:7])
        accounting.generate_rent_invoices(period_month=month, year=year, auto_post=True)

    # ---- Collect most rent (leave some open so ageing has overdue items) ----
    for idx, inv in enumerate(accounting.list_invoices(invoice_type="receivable", limit=300)):
        if idx % 4 == 0:
            continue
        accounting.record_payment(inv["balance"], invoice_id=inv["id"], reference=f"RCPT-{idx:04d}")

    # ---- Operating expenses (6 months) ----
    for i in range(6, 0, -1):
        stamp = months_back(i)
        for code, cat, amount in (
            ("5000", "salaries", 900_000),
            ("5010", "utilities", 180_000),
            ("5020", "maintenance", 120_000),
            ("5030", "property_management", 200_000),
            ("5040", "marketing", 150_000),
        ):
            accounting.create_expense(amount, account_code=code, category=cat, date=stamp,
                                      vendor="Internal", description=f"{cat} — {stamp[:7]}",
                                      scheme_id=lsc_id)
        # depreciation
        accounting.post_journal_entry(
            [{"account": "5070", "debit": 180_000, "description": "Depreciation"},
             {"account": "1350", "credit": 180_000, "description": "Accumulated depreciation"}],
            date=stamp, memo="Monthly depreciation", source="depreciation",
        )
        # service charges income (cash basis)
        accounting.post_journal_entry(
            [{"account": "1010", "debit": 250_000, "description": "Service charges received"},
             {"account": "4020", "credit": 250_000, "description": "Service charges income"}],
            date=stamp, memo="Service charges", source="manual", reference="SC",
        )
        if shop:
            accounting.post_journal_entry(
                [{"account": "1010", "debit": 120_000, "description": "Parking income"},
                 {"account": "4040", "credit": 120_000, "description": "Parking & ancillary income"}],
                date=stamp, memo="Parking income", source="manual",
            )

    # ---- One-off commission income ----
    accounting.post_journal_entry(
        [{"account": "1010", "debit": 1_200_000, "description": "Commission received"},
         {"account": "4030", "credit": 1_200_000, "description": "Commission income"}],
        date=months_back(3), memo="Sale commission — DHA Lahore", source="manual", reference="COM-1",
    )

    # ---- Payable invoice (maintenance contractor) with GST, partly paid ----
    bill = accounting.create_invoice(
        counterparty="FixIt Maintenance Co", invoice_type="payable",
        lines=[{"description": "Annual HVAC & lift maintenance", "quantity": 1,
                "unit_price": 1_500_000, "tax_rate": 0.17}],
        issue_date=months_back(2), due_date=months_back(1), tax_rate=0.17, auto_post=True,
        notes="Contractor maintenance contract",
    )
    if "error" not in bill:
        accounting.record_payment(round(bill["total"] * 0.6), invoice_id=bill["id"], reference="PAY-0001")

    # ---- Budget ----
    accounting.create_budget(
        "FY2026-27 Operating Budget",
        {"5000": 11_000_000, "5010": 2_200_000, "5020": 1_500_000, "5030": 2_400_000, "5040": 1_800_000},
        fiscal_year="2026-27", scope="portfolio",
        notes="Board-approved operating budget.",
    )


def _seed_master_plans() -> None:
    """Register each built DHA master plan as a housing scheme with GIS layers: its outline,
    the georeferenced plan (map tiles) and the PDF's text as annotation layers."""
    if os.getenv("MASTERPLANS_GIS", "1").strip().lower() in ("0", "false", "no", "off") or not masterplan.available():
        return
    for meta in masterplan.store().meta.values():
        city = resolve_city(meta["city"])
        if not city:
            continue
        acc = meta["accuracy"]
        about = (f"Georeferenced from the DHA master plan PDF ({meta.get('pdf')}): {acc.get('method')} fit on "
                 f"{acc.get('gcps')} ground control points" + (f", RMSE {acc['rmse_m']} m" if acc.get("rmse_m") else "") + ".")
        scheme = next((s for s in housing_schemes_db if s.name.lower() == meta["name"].lower()), None)
        if scheme is None:
            scheme = HousingScheme(name=meta["name"], city_id=city.id, latitude=meta["center"][0], longitude=meta["center"][1],
                                   developer="Defence Housing Authority (DHA) Islamabad-Rawalpindi", description=about)
            housing_schemes_db.append(scheme)
        outline = masterplan.outline_geojson(meta)
        gis.add_layer(gis.GeoLayer(name=f"{meta['name']} — boundary", layer_type="boundary", entity_type="scheme",
                                   entity_id=scheme.id, geojson=outline, description=about, source_url=meta.get("pdf"),
                                   style={"color": "#c99a22", "fillColor": "#c99a22", "fillOpacity": 0.05, "weight": 2, "opacity": 0.9}))
        gis.add_layer(gis.GeoLayer(name=f"{meta['name']} — master plan", layer_type="master_plan", entity_type="scheme",
                                   entity_id=scheme.id, geojson=outline, description=about, source_url=meta.get("pdf"),
                                   image_url=masterplan.tile_path(meta["key"]) if meta.get("tiles") else None,
                                   opacity=0.75, z_index=1))
        for title, cats, visible in masterplan.LABEL_GROUPS:
            gis.add_layer(gis.GeoLayer(name=f"{meta['name']} — plan labels: {title}", layer_type="annotation",
                                       entity_type="scheme", entity_id=scheme.id, visible=visible, z_index=2,
                                       geojson=masterplan.geojson_labels(meta["key"], cats),
                                       description=f"Text from the master plan PDF, placed on the ground. {about}",
                                       source_url=meta.get("pdf"),
                                       style={"color": "#1d4ed8", "fillColor": "#1d4ed8", "fillOpacity": 0.8, "weight": 1, "opacity": 0.9}))


def _seed_pois() -> None:
    """Register a realistic set of points of interest around the seeded societies."""
    lsc = resolve_scheme("Lahore Smart City")
    dha_lhr = resolve_scheme("DHA Lahore")
    isb_sc = resolve_scheme("Islamabad Smart City")
    dha_khi = resolve_scheme("DHA Karachi")
    lahore = resolve_city("Lahore")
    islamabad = resolve_city("Islamabad")
    karachi = resolve_city("Karachi")

    rows = [
        # ---- Lahore Smart City ----
        ("Lahore Smart City Grand Mosque", "worship", 31.4510, 74.2802, lsc, lahore, "mosque", 4.8),
        ("Smart City Public School", "education", 31.4495, 74.2790, lsc, lahore, "school", 4.2),
        ("City Care Hospital", "health", 31.4488, 74.2762, lsc, lahore, "hospital", 4.0),
        ("Downtown Shopping Mall", "shopping", 31.4482, 74.2810, lsc, lahore, "mall", 4.4),
        ("Metro Fuel Station", "fuel", 31.4468, 74.2748, lsc, lahore, "petrol", 3.9),
        ("Smart City Central Park", "park", 31.4505, 74.2830, lsc, lahore, "park", 4.5),
        ("HBL — Main Boulevard Branch", "bank", 31.4499, 74.2822, lsc, lahore, "bank", 4.1),
        ("Café Aroma", "restaurant", 31.4508, 74.2840, lsc, lahore, "cafe", 4.3),
        ("Smart City Transport Terminal", "transport", 31.4460, 74.2735, lsc, lahore, "terminal", 3.8),
        ("LDA Zonal Office", "government", 31.4520, 74.2850, lsc, lahore, "office", 3.6),
        # ---- DHA Lahore ----
        ("DHA Phase 6 Grammar School", "education", 31.4705, 74.4140, dha_lhr, lahore, "school", 4.4),
        ("National Hospital DHA", "health", 31.4685, 74.4135, dha_lhr, lahore, "hospital", 4.3),
        ("DHA Y-Block Market", "shopping", 31.4675, 74.4105, dha_lhr, lahore, "market", 4.2),
        ("DHA Grand Jamia Mosque", "worship", 31.4712, 74.4150, dha_lhr, lahore, "mosque", 4.9),
        # ---- Islamabad ----
        ("Islamabad Model School", "education", 33.6810, 73.0430, isb_sc, islamabad, "school", 4.1),
        ("Shifa International Hospital", "health", 33.6795, 73.0415, isb_sc, islamabad, "hospital", 4.6),
        ("Centaurus Mall", "shopping", 33.6835, 73.0450, isb_sc, islamabad, "mall", 4.5),
        ("Faisal Mosque", "worship", 33.6850, 73.0490, isb_sc, islamabad, "mosque", 4.9),
        ("Islamabad Metro Station", "transport", 33.6788, 73.0395, isb_sc, islamabad, "metro", 4.0),
        ("Margalla Hills Trail 5", "park", 33.6870, 73.0515, isb_sc, islamabad, "trail", 4.7),
        # ---- Karachi ----
        ("DHA Suffa University", "education", 24.8150, 67.0320, dha_khi, karachi, "university", 4.3),
        ("Aga Khan Hospital DHA", "health", 24.8130, 67.0290, dha_khi, karachi, "hospital", 4.5),
        ("Dolmen Mall Clifton", "shopping", 24.8105, 67.0280, dha_khi, karachi, "mall", 4.6),
        ("Sea View Beach Park", "park", 24.8080, 67.0300, dha_khi, karachi, "beach", 4.4),
        ("Karachi BRT Red Line Stop", "transport", 24.8160, 67.0340, dha_khi, karachi, "brt", 3.7),
    ]
    for name, category, lat, lon, scheme, city, subcat, rating in rows:
        pois_db.append(
            PointOfInterest(
                name=name, category=category, subcategory=subcat, latitude=lat, longitude=lon,
                city_id=city.id if city else None, scheme_id=scheme.id if scheme else None,
                rating=rating, source="seed",
            )
        )


def _seed_aois() -> None:
    """Create a few saved areas of interest."""
    lsc = resolve_scheme("Lahore Smart City")
    dha_lhr = resolve_scheme("DHA Lahore")
    isb_sc = resolve_scheme("Islamabad Smart City")
    dha_khi = resolve_scheme("DHA Karachi")

    if lsc:
        aois_db.append(
            AreaOfInterest(
                name="Lahore Smart City — Watch Area", kind="entity", entity_type="scheme",
                entity_id=lsc.id, scheme_id=lsc.id,
                description="Flagship new society; tracking approvals and pricing.",
                tags=["flagship", "growth"],
                watch_categories=["regulation", "development", "market"],
                watch_alert_threshold=30.0,
            )
        )
    if dha_lhr:
        aois_db.append(
            AreaOfInterest(
                name="DHA Lahore Phase 6 — 1 km Radius", kind="circle",
                center_latitude=31.4690, center_longitude=74.4120, radius_m=1000.0,
                scheme_id=dha_lhr.id,
                description="Mature, high-liquidity residential pocket.",
                tags=["mature", "residential"],
                watch_categories=["market", "infrastructure"],
                watch_alert_threshold=25.0,
            )
        )
    if isb_sc:
        aois_db.append(
            AreaOfInterest(
                name="Islamabad Smart City Polygon", kind="polygon",
                coordinates=[[33.5150, 73.0450], [33.5150, 73.0650], [33.5300, 73.0650], [33.5300, 73.0450]],
                scheme_id=isb_sc.id,
                description="Master-plan footprint used for supply and pricing analysis.",
                tags=["supply", "capital"],
                watch_categories=["development", "policy"],
                watch_alert_threshold=35.0,
            )
        )
    if dha_khi:
        aois_db.append(
            AreaOfInterest(
                name="Karachi Sea View Corridor", kind="circle",
                center_latitude=24.8130, center_longitude=67.0300, radius_m=1500.0,
                scheme_id=dha_khi.id,
                description="Premium coastal corridor with strong end-user demand.",
                tags=["premium", "coastal"],
                watch_categories=["regulation", "market", "infrastructure"],
                watch_alert_threshold=30.0,
            )
        )


def _seed_content() -> None:
    """Seed the public portal: editorial pages, company history, contacts,
    success stories and a rich advertisement book (smart technology, modern
    construction techniques, building-material availability, solar, finance …)."""
    lahore = resolve_city("Lahore")
    karachi = resolve_city("Karachi")
    islamabad = resolve_city("Islamabad")
    lsc = resolve_scheme("Lahore Smart City")
    dha_lhr = resolve_scheme("DHA Lahore")
    isb_sc = resolve_scheme("Islamabad Smart City")
    dha_khi = resolve_scheme("DHA Karachi")

    # ---- Content pages ----
    content.pages_db.extend([
        content.PortalPage(
            key="about", title="About Arz-e-Pak", category="about", order=10,
            nav_label="About", subtitle="Pakistan's smart, data-driven property marketplace",
            summary="Two decades of connecting Pakistani families, investors and developers.",
            body=[
                "Arz-e-Pak is a full-stack real-estate portal built for Pakistan. From the "
                "tree-lined streets of DHA Lahore to the coastline of DHA Karachi and the "
                "planned sectors of Islamabad, we map every city, society, block and property "
                "into one navigable, data-rich platform.",
                "Our catalogue is organised as a strict hierarchy — City → Housing Scheme / "
                "Society → Block / Zone / Area → Property — so buyers can zoom from a national "
                "overview down to a single plot. Every entity carries GIS coordinates, master-plan "
                "layers, imagery, floor plans, amenities and multimedia.",
                "Behind the listings sits an analytics core: geographic search, points and areas "
                "of interest, valuation and ROI models, double-entry accounting, a CRM pipeline "
                "and multi-factor forecasting — all exposed through an open MCP and REST API.",
            ],
            highlights=[
                {"label": "Founded", "value": "2005", "sub": "Lahore, Pakistan"},
                {"label": "Cities", "value": "4+", "sub": "Lahore · Karachi · Islamabad · Rawalpindi"},
                {"label": "Verified listings", "value": "100k+", "sub": "across societies"},
                {"label": "Team", "value": "180+", "sub": "agents, valuers & engineers"},
            ],
            bullets=[
                "Verified listings with documented title checks",
                "GIS master-plan mapping and polygon search",
                "Instant valuation, ROI and future-price forecasts",
                "Bilingual (English / اردو) experience with light and dark themes",
            ],
            tags=["company", "portal"],
        ),
        content.PortalPage(
            key="mission", title="Our Mission & Values", category="mission", order=20,
            nav_label="Mission", subtitle="Making property decisions transparent and data-driven",
            body=[
                "We exist to remove the guesswork from Pakistani real estate. Every price, "
                "yield, distance and forecast shown on the portal is backed by data and a "
                "method behind it — never an unsupported claim.",
                "We believe a family buying its first home deserves the same analytical rigour "
                "as an institutional investor, and that trust is the only sustainable currency "
                "in this market.",
            ],
            bullets=[
                "Transparency — sources, assumptions and methods are always visible",
                "Accuracy — valuations reconciled against comparables and rent rolls",
                "Inclusion — affordable housing and low-cost finance are first-class citizens",
                "Responsibility — verified titles and clean documentation",
            ],
            tags=["company", "values"],
        ),
        content.PortalPage(
            key="services", title="What We Offer", category="services", order=30,
            nav_label="Services", subtitle="End-to-end property services",
            summary="From discovery to handover and beyond.",
            body=[
                "Whether you are buying, selling, renting, investing or developing, the portal "
                "carries you through the whole lifecycle with tools for each stage.",
            ],
            highlights=[
                {"label": "Buy & Sell", "value": "Listings + CRM", "sub": "verified inventory"},
                {"label": "Rent", "value": "Rent roll", "sub": "leases & yields"},
                {"label": "Invest", "value": "ROI / IRR", "sub": "scenario modelling"},
                {"label": "Develop", "value": "Cost & feasibility", "sub": "GDV, margin, break-even"},
                {"label": "Analyse", "value": "GIS + forecast", "sub": "POI, AOI, predictions"},
                {"label": "Finance", "value": "Mortgages", "sub": "bank & subsidy schemes"},
            ],
            bullets=[
                "Advertising desk for builders, material suppliers and service providers",
                "Project marketing for malls, towers, mixed-use buildings, compounds and plazas",
                "Landlord services: listing, tenant screening, rent collection",
                "Valuation reports for banks, courts and taxation",
            ],
            tags=["services"],
        ),
        content.PortalPage(
            key="why-us", title="Why Arz-e-Pak", category="why-us", order=40,
            nav_label="Why Us", subtitle="The advantages our clients keep telling us about",
            body=[
                "Property is the largest purchase most Pakistanis ever make. We built the "
                "portal so that decision is made with evidence, not hearsay.",
            ],
            bullets=[
                "One hierarchy, whole country — cities, societies and blocks in one map",
                "Live analytics — market value, rent roll, composite market index",
                "Verified supply — title and ownership checks on premium inventory",
                "Developer-grade tools — feasibility, cost and economic-impact modelling",
                "Bilingual and accessible on any device, in light or dark mode",
            ],
            tags=["company", "marketing"],
        ),
        content.PortalPage(
            key="how-it-works", title="How It Works", category="help", order=45,
            nav_label="How It Works", subtitle="Four steps from search to keys",
            body=[
                "Arz-e-Pak follows a simple, repeatable path so nothing is left to chance.",
            ],
            highlights=[
                {"label": "1. Search", "value": "Map first", "sub": "filter by city, society, block"},
                {"label": "2. Verify", "value": "Documents", "sub": "title, approvals, NOC"},
                {"label": "3. Analyse", "value": "Numbers", "sub": "value, yield, forecast"},
                {"label": "4. Transact", "value": "Handover", "sub": "finance, transfer, possession"},
            ],
            faqs=[
                {"question": "Do I need an account to browse?",
                 "answer": "No. Browsing and maps are open; an account (verified by mobile or e-mail OTP) unlocks saved searches, offers and messaging."},
                {"question": "How are prices validated?",
                 "answer": "Prices are reconciled against comparable listings, recent transactions and rent rolls, and flagged when a listing deviates sharply from the market band."},
                {"question": "Can I book a site visit?",
                 "answer": "Yes — every listing page lets you request a visit, which the CRM routes to the assigned agent with a scheduled slot."},
            ],
            tags=["help", "onboarding"],
        ),
        content.PortalPage(
            key="team", title="People Behind the Portal", category="team", order=50,
            nav_label="Team", subtitle="Agents, valuers, engineers and analysts",
            body=[
                "Our teams combine on-the-ground market knowledge with data science and "
                "engineering. Regional desks in Lahore, Karachi and Islamabad are supported by "
                "a central analytics group.",
            ],
            highlights=[
                {"label": "Operations", "value": "90", "sub": "agents & support"},
                {"label": "Valuation", "value": "35", "sub": "certified valuers"},
                {"label": "Engineering", "value": "30", "sub": "GIS & platform"},
                {"label": "Analytics", "value": "25", "sub": "data & research"},
            ],
            tags=["team"],
        ),
        content.PortalPage(
            key="careers", title="Careers", category="careers", order=60,
            nav_label="Careers", subtitle="Build the future of Pakistani real estate with us",
            body=[
                "We hire for curiosity, rigour and care. If you want to work where technology "
                "meets the bricks and mortar of a fast-urbanising country, you will find a home here.",
            ],
            bullets=[
                "Field sales & customer success (Lahore / Karachi / Islamabad)",
                "GIS & urban-data analysts",
                "Full-stack engineers and data scientists",
                "Certified valuers and quantity surveyors",
            ],
            faqs=[
                {"question": "Do you offer internships?",
                 "answer": "Yes — a structured 12-week programme across sales, analytics and engineering runs twice a year."},
            ],
            tags=["careers"],
        ),
        content.PortalPage(
            key="faq", title="Frequently Asked Questions", category="faq", order=70,
            nav_label="FAQ", subtitle="Answers to the questions we hear most",
            body=["Everything you need to know about listings, verification, finance and the API."],
            faqs=[
                {"question": "How do I verify a listing?",
                 "answer": "Verified listings display a badge; their title, developer NOC and plot dimensions have been checked against society records."},
                {"question": "Which areas do you cover?",
                 "answer": "Currently Lahore, Karachi, Islamabad and Rawalpindi, with schemes, blocks, properties, points of interest and master plans modelled for each."},
                {"question": "Can I get a mortgage through the portal?",
                 "answer": "Yes. We surface bank and SBP-subsidised home-finance offers and provide a mortgage calculator with amortisation schedules."},
                {"question": "Is there an API?",
                 "answer": "Yes — every capability is exposed over both MCP (for AI agents) and REST (for applications), backed by the same logic."},
                {"question": "Do you support Urdu?",
                 "answer": "Fully. The portal renders right-to-left in Urdu and can be switched between languages and light/dark themes at any time."},
            ],
            tags=["help", "faq"],
        ),
        content.PortalPage(
            key="terms", title="Terms of Use", category="legal", order=80,
            nav_label="Terms", subtitle="The ground rules for using Arz-e-Pak",
            body=[
                "By using the portal you agree to provide accurate information, to use listing "
                "data for lawful purposes only, and to respect the intellectual-property rights "
                "of the portal and its advertisers.",
                "Listing figures, valuations and forecasts are estimates provided for guidance "
                "and do not constitute a guarantee of price, yield or future performance.",
            ],
            bullets=[
                "Accounts must be verified by OTP before transactional features unlock",
                "Automated scraping of listing data is not permitted without a licence",
                "Advertisers are responsible for the accuracy of their creatives",
            ],
            tags=["legal", "policy"],
        ),
        content.PortalPage(
            key="privacy", title="Privacy Policy", category="policy", order=90,
            nav_label="Privacy", subtitle="How we handle your data",
            body=[
                "We collect only the information needed to operate the portal: contact "
                "details, saved searches and interaction history. Verification codes and "
                "session tokens are stored securely and expire automatically.",
                "We never sell personal data. Aggregated, de-identified market statistics may "
                "be shared with research partners.",
            ],
            bullets=[
                "OTP-verified accounts with expiring sessions",
                "Role-based access controls across staff and portal areas",
                "Audit trail for every authentication and permission event",
            ],
            tags=["legal", "privacy"],
        ),
    ])

    # ---- Company history timeline ----
    history_rows = [
        (2005, 3, "founding", "Arz-e-Pak is founded in Lahore",
         "Three agents and an engineer start the firm with a simple idea: document every deal.", True),
        (2007, 8, "milestone", "First 1,000 listings catalogued",
         "Manual field surveys turn into a searchable printed and online register.", False),
        (2009, 6, "expansion", "Karachi office opens",
         "Coastal demand drives a second regional desk serving DHA and Clifton.", False),
        (2011, 4, "technology", "Online listing portal launched",
         "The catalogue moves to the web with searchable society, block and plot records.", False),
        (2013, 9, "partnership", "Mortgage-facilitation partnerships signed with leading banks",
         "Pre-approved home finance becomes available directly on qualifying listings.", False),
        (2015, 11, "award", "Best Real Estate Portal — Pakistan Digital Awards",
         "National recognition for transparency and data quality.", True),
        (2016, 5, "expansion", "Islamabad office; nationwide coverage reached",
         "The capital's planned sectors complete the Lahore–Karachi–Islamabad triangle.", False),
        (2018, 2, "technology", "GIS master-plan mapping introduced",
         "Society master plans, zone layouts and plot boundaries become map layers.", True),
        (2019, 12, "financial", "PKR 1 billion in facilitated transactions crossed",
         "Cumulative verified deal value passes the billion-rupee mark.", False),
        (2021, 7, "technology", "Mobile app and instant valuation engine launched",
         "Automated comparable-based valuation returns a value band in seconds.", False),
        (2022, 10, "milestone", "100,000 verified listings",
         "Inventory and verification pipelines scale across four cities.", True),
        (2023, 6, "partnership", "Smart-city data partnerships with major developers",
         "Live phase releases, pricing and availability flow from developers into the portal.", False),
        (2024, 3, "technology", "AI valuation, ROI and multi-factor forecast engine",
         "Development, infrastructure, economic and regulatory factors fold into one outlook.", True),
        (2025, 9, "recognition", "ISO 27001 information-security certification",
         "Independent audit of the handling of listings data and personal information.", False),
        (2026, 1, "milestone", "Open MCP + REST API and bilingual portals",
         "Every capability is exposed to AI agents and applications alike, in English and Urdu.", True),
    ]
    for year, month, kind, title, desc, featured in history_rows:
        content.history_db.append(content.HistoryEntry(
            year=year, month=month, kind=kind, title=title, description=desc,
            featured=featured, tags=["history", kind],
        ))

    # ---- Contact directory ----
    content.contacts_db.extend([
        content.ContactChannel(channel_type="phone", label="Call centre", value="+92 42 111 000 000",
                               is_primary=True, priority=10, hours="Mon–Sat, 9am–8pm",
                               notes="General enquiries and listing support."),
        content.ContactChannel(channel_type="helpline", label="24/7 helpline", value="+92 42 111 000 111",
                               priority=15, hours="24 hours", notes="Urgent listing and fraud reports."),
        content.ContactChannel(channel_type="whatsapp", label="WhatsApp", value="+92 300 000 0000",
                               url="https://wa.me/923000000000", priority=20,
                               notes="Send a plot number to get instant details."),
        content.ContactChannel(channel_type="email", label="General enquiries", value="hello@arzeapak.pk",
                               url="mailto:hello@arzeapak.pk", is_primary=True, priority=10),
        content.ContactChannel(channel_type="email", label="Advertising desk", value="ads@arzeapak.pk",
                               url="mailto:ads@arzeapak.pk", priority=30,
                               notes="Place a campaign across portal slots."),
        content.ContactChannel(channel_type="office", label="Head office — Lahore", value="Main Boulevard, Gulberg III, Lahore",
                               url="https://maps.google.com/?q=Gulberg+Lahore", is_primary=True, priority=10,
                               hours="Mon–Sat, 9am–6pm"),
        content.ContactChannel(channel_type="office", label="Karachi office", value="Ittehad Commercial, DHA Phase 6, Karachi",
                               city_id=karachi.id if karachi else None, priority=40, hours="Mon–Sat, 9am–6pm"),
        content.ContactChannel(channel_type="office", label="Islamabad office", value="Blue Area, Jinnah Avenue, Islamabad",
                               city_id=islamabad.id if islamabad else None, priority=40, hours="Mon–Sat, 9am–6pm"),
        content.ContactChannel(channel_type="hours", label="Office hours", value="Monday to Saturday, 9:00 am – 6:00 pm",
                               priority=50, notes="Closed on public holidays."),
        content.ContactChannel(channel_type="social", label="Facebook", value="facebook.com/arzeapak",
                               url="https://facebook.com/arzeapak", priority=60),
        content.ContactChannel(channel_type="social", label="Instagram", value="instagram.com/arzeapak",
                               url="https://instagram.com/arzeapak", priority=60),
        content.ContactChannel(channel_type="social", label="YouTube", value="youtube.com/@arzeapak",
                               url="https://youtube.com/@arzeapak", priority=65),
        content.ContactChannel(channel_type="website", label="Website", value="www.arzeapak.pk",
                               url="https://www.arzeapak.pk", priority=70),
        content.ContactChannel(channel_type="chat", label="Live chat", value="Chat with an agent",
                               url="https://www.arzeapak.pk/chat", priority=25, hours="Mon–Sat, 9am–8pm"),
    ])

    # ---- Success stories ----
    content.stories_db.extend([
        content.SuccessStory(
            title="Hassan's family finds a turnkey smart home in Lahore Smart City",
            story_type="case_study", client_name="Hassan Raza", client_role="First-time buyer",
            quote="We compared eleven houses on the map and the valuation model told us exactly which plots were overpriced. We closed in six weeks.",
            rating=5.0, location="Sector A, Lahore Smart City", scheme_id=lsc.id if lsc else None,
            narrative=[
                "Hassan and his family were relocating from Dubai and needed a completed, "
                "solar-ready house near schools and a mosque.",
                "Using the portal's POI accessibility scores and valuation band, they shortlisted "
                "three homes and negotiated with evidence rather than emotion.",
            ],
            metrics=[{"label": "Saved vs asking", "value": "Rs 3.2M"},
                     {"label": "Time to close", "value": "6 weeks"},
                     {"label": "Accessibility score", "value": "48.2"}],
            highlights=["10 Marla house", "Solar system included", "Verified title"],
            featured=True, date="2025-11-02", tags=["residential", "smart-home"],
        ),
        content.SuccessStory(
            title="A commercial plot flipped into a thriving retail arcade",
            story_type="investment", client_name="Fatima Noor", client_role="Investor",
            quote="The economic-impact analysis convinced me the footfall was there. The arcade was fully let within a quarter.",
            rating=4.8, location="Commercial Downtown, Lahore Smart City", scheme_id=lsc.id if lsc else None,
            narrative=[
                "A 2-kanal commercial plot sat under-priced because buyers under-estimated "
                "the surrounding catchment.",
                "The portal's population, spend and accessibility analysis projected the retail "
                "demand; the client developed a small arcade of shops and offices.",
            ],
            metrics=[{"label": "Capital employed", "value": "Rs 180M"},
                     {"label": "Projected IRR", "value": "34.6%"},
                     {"label": "Let-up", "value": "100% in 3 months"}],
            highlights=["2 Kanal commercial", "Mixed-use development", "Strong catchment"],
            featured=True, date="2025-08-19", tags=["investment", "commercial"],
        ),
        content.SuccessStory(
            title="Sea-view apartment rented 11 months a year",
            story_type="case_study", client_name="Sara Ahmed", client_role="Landlord",
            quote="The rent roll and yield tools let me price the apartment correctly the first time — no long void periods.",
            rating=4.9, location="DHA Karachi",
            scheme_id=dha_khi.id if dha_khi else None, city_id=karachi.id if karachi else None,
            narrative=[
                "An overseas landlord needed hands-off management and reliable rental income.",
                "Comparable-rent analysis set a realistic asking rent; tenant screening and "
                "digitised lease tracking kept occupancy high.",
            ],
            metrics=[{"label": "Annual occupancy", "value": "91%"},
                     {"label": "Gross yield", "value": "5.4%"},
                     {"label": "Time to tenant", "value": "12 days"}],
            highlights=["4-bed apartment", "Sea view", "Managed leasing"],
            featured=False, date="2025-06-30", tags=["rental", "yield"],
        ),
        content.SuccessStory(
            title="A developer pre-sold a tower using portal master-plan layers",
            story_type="project", client_name="Skyline Developers", client_role="Developer",
            quote="Interactive master plans and unit availability gave overseas buyers the confidence to book before launch.",
            location="Islamabad Smart City", scheme_id=isb_sc.id if isb_sc else None,
            narrative=[
                "A mid-rise residential tower needed pre-launch demand to secure construction finance.",
                "Interactive floor plates, unit mix and phased pricing on the portal converted "
                "diaspora interest into bookings.",
            ],
            metrics=[{"label": "Units pre-sold", "value": "68%"},
                     {"label": "Bookings value", "value": "Rs 1.4B"},
                     {"label": "Overseas share", "value": "44%"}],
            highlights=["22 floors", "Mixed-use podium", "Diaspora campaign"],
            featured=True, date="2025-09-12", tags=["project", "pre-launch"],
        ),
        content.SuccessStory(
            title="An overseas investor built a diversified three-city portfolio",
            story_type="investment", client_name="Usman Tariq", client_role="Overseas investor",
            quote="One dashboard for Lahore, Karachi and Islamabad — valuations, rents and forecasts in a single view.",
            rating=5.0, location="Lahore · Karachi · Islamabad",
            narrative=[
                "The client wanted exposure to three markets without travelling to inspect each asset.",
                "Verified listings, remote valuations and ROI modelling built a balanced portfolio.",
            ],
            metrics=[{"label": "Assets", "value": "7 across 3 cities"},
                     {"label": "Blended yield", "value": "6.1%"},
                     {"label": "5-yr forecast CAGR", "value": "10.3%"}],
            highlights=["Diversified", "Hands-off", "Data-driven"],
            featured=False, date="2025-04-21", tags=["investment", "portfolio"],
        ),
        content.SuccessStory(
            title="Trusted by a bank for mortgage valuation reports",
            story_type="milestone", client_name="National Housing Bank", client_role="Institution",
            quote="Consistent, defensible valuations that our credit committee can rely on.",
            location="Nationwide",
            narrative=[
                "A lender needed standardised valuation reports at scale for its home-finance book.",
                "The portal's valuation engine and report templates now back the bank's approvals.",
            ],
            metrics=[{"label": "Reports / month", "value": "450+"},
                     {"label": "Turnaround", "value": "48 hours"},
                     {"label": "Markets", "value": "4 cities"}],
            highlights=["Institutional", "Standardised", "Auditable"],
            featured=False, date="2025-02-08", tags=["valuation", "institutional"],
        ),
        content.SuccessStory(
            title="A landlord's 6-flat block reached 97% occupancy",
            story_type="testimonial", client_name="Bilal Chaudhry", client_role="Landlord",
            quote="Tenant screening and digital leases cut my vacancy and my paperwork at the same time.",
            rating=4.7, location="DHA Lahore", scheme_id=dha_lhr.id if dha_lhr else None,
            narrative=[
                "Managing six flats across two buildings was consuming weekends.",
                "The portal's landlord tools centralised listings, screening, rent collection and renewals.",
            ],
            metrics=[{"label": "Occupancy", "value": "97%"},
                     {"label": "Rent collected on time", "value": "94%"},
                     {"label": "Admin time", "value": "-60%"}],
            highlights=["6 flats", "Managed", "Screen tenants"],
            featured=False, date="2024-12-15", tags=["rental", "landlord"],
        ),
    ])

    # ---- Advertisement book ----
    ads = [
        dict(title="SmartNest Home Automation", headline="Make your home think ahead",
             advertiser="SmartNest Pakistan", category="smart_technology", slot="hero",
             body="Smart switches, app-controlled lighting, smart locks and AI-assisted CCTV — "
                  "installed and warrantied across Lahore, Karachi and Islamabad.",
             cta_label="Get a free demo", cta_url="https://example.com/demo",
             phone="+92 21 111 111 111", price_text="Packages from Rs 185,000",
             offer="20% off during launch month", priority=10, weight=2.0,
             budget=1_500_000, spend=420_000, impressions=18_400, clicks=510,
             keywords=["smart home", "automation", "iot"], tags=["smart_technology", "home"],
             lang="en"),
        dict(title="Tunnel-Form Construction", headline="Faster floors, stronger cores",
             advertiser="BuildTech Pakistan", category="construction_technique", slot="banner",
             body="Aluminium tunnel formwork and jump-form systems that cut slab cycles and "
                  "improve finish quality for high-rise residential towers.",
             cta_label="See case studies", cta_url="https://example.com/formwork",
             phone="+92 42 222 222 222", price_text="Consultation free",
             offer="Feasibility study included", priority=20, weight=1.4,
             budget=900_000, spend=180_000, impressions=11_200, clicks=286,
             keywords=["formwork", "construction", "tower"], tags=["construction_technique"],
             lang="en"),
        dict(title="ICF & Precast Systems", headline="Insulated concrete, built to last",
             advertiser="InsulBuild Systems", category="construction_technique", slot="infeed",
             body="Insulated concrete formwork and precast wall panels deliver thermal efficiency "
                  "and monsoon resilience with dramatically reduced on-site labour.",
             cta_label="Request a quote", cta_url="https://example.com/quote",
             phone="+92 51 333 333 333", price_text="From Rs 3,100 / sq ft",
             priority=30, weight=1.2, budget=600_000, spend=95_000,
             impressions=8_400, clicks=167, keywords=["icf", "precast", "insulation"],
             tags=["construction_technique", "materials"], lang="en"),
        dict(title="Cement & Steel Availability", headline="Verified stock, delivered to site",
             advertiser="PakBuild Materials", category="materials", slot="sidebar",
             body="OPC and sulphate-resistant cement, Grade-60 steel and A-class bricks with "
                  "same-week delivery and quantity certification.",
             cta_label="Check live rates", cta_url="https://example.com/rates",
             phone="+92 42 444 444 444", price_text="Cement from Rs 1,285 / bag",
             offer="Bulk discount above 500 bags", priority=15, weight=1.6,
             budget=750_000, spend=210_000, impressions=14_900, clicks=402,
             keywords=["cement", "steel", "bricks", "materials"], tags=["materials", "rates"],
             lang="en"),
        dict(title="Concrete Pumps & Tower Cranes", headline="Rent the right machine, on time",
             advertiser="MachineryLink Pakistan", category="tools_equipment", slot="infeed",
             body="Boom pumps, transit mixers, tower cranes and telehandlers on daily or "
                  "project terms with trained operators.",
             cta_label="Browse fleet", cta_url="https://example.com/fleet",
             phone="+92 21 555 555 555", price_text="Crane from Rs 42,000 / day",
             priority=35, weight=1.1, budget=500_000, spend=60_000,
             impressions=6_300, clicks=121, keywords=["crane", "pump", "equipment"],
             tags=["tools_equipment"], lang="en"),
        dict(title="SolarMax Net Metering", headline="Cut your bill by up to 90%",
             advertiser="SolarMax Energy", category="solar_energy", slot="infeed",
             body="Tier-1 panels, hybrid inverters and net-metering paperwork handled end to "
                  "end — from 5 kW homes to 100 kW buildings.",
             cta_label="Calculate savings", cta_url="https://example.com/savings",
             phone="+92 42 666 666 666", price_text="10 kW from Rs 1,150,000",
             offer="Free shading analysis", priority=18, weight=1.8,
             budget=1_200_000, spend=330_000, impressions=16_700, clicks=498,
             keywords=["solar", "net metering", "renewable"], tags=["solar_energy", "energy"],
             lang="en"),
        dict(title="AquaPure Filtration", headline="Clean water, from tank to tap",
             advertiser="AquaPure Pakistan", category="water", slot="sidebar",
             body="Whole-building filtration, RO plants and pressure systems with annual "
                  "maintenance for homes, mosques and housing societies.",
             cta_label="Book a survey", cta_url="https://example.com/survey",
             phone="+92 21 777 777 777", price_text="RO plant from Rs 95,000",
             priority=40, weight=1.0, budget=350_000, spend=42_000,
             impressions=5_100, clicks=88, keywords=["water", "filtration", "ro"],
             tags=["water"], lang="en"),
        dict(title="SecureVision Access Control", headline="Your society, only your people",
             advertiser="SecureVision", category="security", slot="banner",
             body="Biometric gates, ANPR vehicle recognition, visitor management and "
                  "24/7 monitoring integrated into one control room.",
             cta_label="Talk to sales", cta_url="https://example.com/contact",
             phone="+92 51 888 888 888", price_text="Societies from Rs 2.4M",
             priority=25, weight=1.3, budget=800_000, spend=150_000,
             impressions=9_800, clicks=214, keywords=["security", "biometric", "anpr"],
             tags=["security", "gated-community"], lang="en"),
        dict(title="Elevate Lifts & Parking", headline="Vertical living, solved",
             advertiser="Elevate Engineering", category="elevators", slot="infeed",
             body="Passenger and freight lifts, car stackers and basement parking systems "
                  "with 24/7 service contracts.",
             cta_label="Get engineered spec", cta_url="https://example.com/spec",
             phone="+92 42 999 999 999", price_text="Lifts from Rs 3,600,000",
             priority=45, weight=1.0, budget=400_000, spend=55_000,
             impressions=4_600, clicks=73, keywords=["lift", "elevator", "parking"],
             tags=["elevators"], lang="en"),
        dict(title="Interior Studio Complete Fit-outs", headline="Turnkey interiors in 45 days",
             advertiser="Interior Studio", category="interiors", slot="infeed",
             body="Design, joinery, flooring, kitchens and wardrobes delivered as one "
                  "turnkey package with a fixed timeline.",
             cta_label="See portfolio", cta_url="https://example.com/portfolio",
             phone="+92 21 121 212 121", price_text="From Rs 1,850 / sq ft",
             offer="Free 3D concept", priority=50, weight=1.0, budget=450_000,
             spend=48_000, impressions=5_900, clicks=140,
             keywords=["interior", "fit-out", "kitchen"], tags=["interiors"], lang="en"),
        dict(title="GreenScape Landscaping", headline="Gardens that survive the summer",
             advertiser="GreenScape Lahore", category="landscaping", slot="footer",
             body="Drought-tolerant planting, irrigation design, lawns and hardscape for "
                  "homes and society green belts.",
             cta_label="Request design", cta_url="https://example.com/design",
             phone="+92 42 313 131 313", price_text="Lawns from Rs 220 / sq ft",
             priority=60, weight=1.0, budget=250_000, spend=22_000,
             impressions=3_400, clicks=51, keywords=["landscape", "garden", "lawn"],
             tags=["landscaping"], lang="en"),
        dict(title="Noor Islamic Home Finance", headline="Own your home the halal way",
             advertiser="Noor Home Finance", category="finance", slot="hero",
             body="Shariah-compliant Diminishing Musharakah home finance with tenures up "
                  "to 25 years and fast pre-approval for verified listings.",
             cta_label="Check eligibility", cta_url="https://example.com/home-finance",
             phone="+92 21 111 111 425", price_text="Mark-up from 12.5% p.a.",
             offer="Processing fee waived this quarter", priority=8, weight=2.2,
             budget=2_000_000, spend=640_000, impressions=24_600, clicks=812,
             keywords=["mortgage", "home finance", "islamic"], tags=["finance", "mortgage"],
             lang="en"),
        dict(title="Mark-up Subsidy Guide", headline="Subsidised finance for first homes",
             advertiser="HomeStart Advisory", category="finance", slot="banner",
             body="Low-income and middle-income housing finance tiers with subsidised "
                  "mark-up for eligible first-time buyers.",
             cta_label="Read the tiers", cta_url="https://example.com/housing",
             price_text="Mark-up from 5% (subsidised)",
             priority=12, weight=1.5, budget=0, impressions=13_100, clicks=356,
             keywords=["subsidy", "affordable housing", "sbp"], tags=["finance", "policy"],
             lang="en"),
        dict(title="SafeNest Property Insurance", headline="Protect the asset, not just the loan",
             advertiser="SafeNest Insurance", category="insurance", slot="sidebar",
             body="Fire, theft, flood and title-risk cover with claims support for "
                  "homeowners, landlords and societies.",
             cta_label="Get a premium", cta_url="https://example.com/property",
             phone="+92 21 111 000 880", price_text="Buildings from Rs 12,000 / year",
             priority=55, weight=1.0, budget=300_000, spend=33_000,
             impressions=4_100, clicks=64, keywords=["insurance", "property", "cover"],
             tags=["insurance"], lang="en"),
        dict(title="Shield Title & Documentation", headline="Clean titles, no surprises",
             advertiser="Shield Legal Services", category="legal", slot="infeed",
             body="Title verification, NOC checks, mutation and transfer documentation "
                  "handled by property-law specialists.",
             cta_label="Book a title check", cta_url="https://example.com/title-check",
             phone="+92 42 005 555 005", price_text="Title check from Rs 25,000",
             priority=48, weight=1.1, budget=200_000, spend=19_000,
             impressions=3_700, clicks=97, keywords=["title", "legal", "noc"],
             tags=["legal", "due-diligence"], lang="en"),
        dict(title="MoveEasy Relocation", headline="Shift home in a single day",
             advertiser="MoveEasy Pakistan", category="services", slot="footer",
             body="Packing, moving, storage and utility transfers with insured handling "
                  "across all major cities.",
             cta_label="Book a move", cta_url="https://example.com/book",
             phone="+92 21 616 161 616", price_text="Local moves from Rs 45,000",
             priority=65, weight=1.0, budget=150_000, spend=14_000,
             impressions=2_900, clicks=47, keywords=["moving", "relocation", "storage"],
             tags=["services"], lang="en"),
        dict(title="FixIt Home Maintenance", headline="One number for every repair",
             advertiser="FixIt Pakistan", category="services", slot="newsletter",
             body="Vetted electricians, plumbers, AC technicians and handymen on demand, "
                  "with a workmanship guarantee.",
             cta_label="Subscribe & book", cta_url="https://example.com/plans",
             price_text="Annual plan from Rs 18,000", priority=58, weight=1.2,
             budget=220_000, spend=26_000, impressions=4_800, clicks=112,
             keywords=["maintenance", "repair", "services"], tags=["services", "maintenance"],
             lang="en"),
        dict(title="گھر کے لیے اسمارٹ ٹیکنالوجی", headline="اسمارٹ کیمرے اور لائٹس، ایک ہی ایپ سے",
             advertiser="SmartNest Pakistan", category="smart_technology", slot="infeed",
             body="اسمارٹ سوئچ، اسمارٹ لاک اور مصنوعی ذہانت والے کیمرے — لاہور، کراچی اور "
                  "اسلام آباد میں تنصیب کے ساتھ۔",
             cta_label="مفت ڈیمو لیں", cta_url="https://example.com/ur",
             phone="+92 21 111 111 111", price_text="پیکج 185,000 روپے سے",
             priority=11, weight=1.4, budget=400_000, spend=58_000,
             impressions=6_700, clicks=158, keywords=["اسمارٹ", "سیکیورٹی"],
             tags=["smart_technology", "urdu"], lang="ur"),
        dict(title="تعمیراتی سیمنٹ اور سریا", headline="اصلی ریٹ، بروقت ڈیلیوری",
             advertiser="PakBuild Materials", category="materials", slot="banner",
             body="او پی سی سیمنٹ، گریڈ 60 سریا اور اے کلاس اینٹیں — مقدار کی تصدیق کے "
                  "ساتھ ہفتے کے اندر ڈیلیوری۔",
             cta_label="آج کے ریٹ دیکھیں", cta_url="https://example.com/ur",
             phone="+92 42 444 444 444", price_text="سیمنٹ 1,285 روپے فی بوری سے",
             priority=16, weight=1.3, budget=350_000, spend=44_000,
             impressions=5_400, clicks=126, keywords=["سیمنٹ", "سریا", "میٹریل"],
             tags=["materials", "urdu"], lang="ur"),
        dict(title="سولر نیٹ میٹرنگ", headline="بجلی کا بل 90% تک کم کریں",
             advertiser="SolarMax Energy", category="solar_energy", slot="infeed",
             body="ٹائر-1 سولر پینل، ہائبرڈ انورٹر اور نیٹ میٹرنگ کی مکمل کارروائی — گھر "
                  "سے بڑی عمارتوں تک۔",
             cta_label="بچت معلوم کریں", cta_url="https://example.com/ur",
             phone="+92 42 666 666 666", price_text="10 کلو واٹ 1,150,000 روپے سے",
             priority=19, weight=1.5, budget=500_000, spend=61_000,
             impressions=7_200, clicks=174, keywords=["سولر", "بجلی"], tags=["solar_energy", "urdu"],
             lang="ur"),
        dict(title="اسلامی ہوم فنانس", headline="شرعی اصولوں کے مطابق اپنا گھر بنائیں",
             advertiser="Noor Home Finance", category="finance", slot="sidebar",
             body="مشارکہ پر مبنی ہوم فنانس، 25 سال تک کی آسانیاں اور تصدیق شدہ "
                  "لسٹنگز پر فوری منظوری۔",
             cta_label="اہلیت چیک کریں", cta_url="https://example.com/ur-home-finance",
             phone="+92 21 111 111 425", price_text="منافع 12.5% سالانہ سے",
             priority=14, weight=1.4, budget=450_000, spend=52_000,
             impressions=6_100, clicks=141, keywords=["فنانس", "مورگیج"], tags=["finance", "urdu"],
             lang="ur"),
        dict(title="سیکیورٹی اور ایکسس کنٹرول", headline="سوسائٹی میں صرف آپ کے لوگ",
             advertiser="SecureVision", category="security", slot="footer",
             body="بائیو میٹرک گیٹ، نمبر پلیٹ سے گاڑی کی شناخت اور وزٹر مینجمنٹ — ایک "
                  "کنٹرول روم سے۔",
             cta_label="ہم سے رابطہ کریں", cta_url="https://example.com/ur",
             phone="+92 51 888 888 888", price_text="سوسائٹی پیکج 2.4 ملین سے",
             priority=27, weight=1.1, budget=250_000, spend=28_000,
             impressions=3_900, clicks=79, keywords=["سیکیورٹی", "گیٹ"], tags=["security", "urdu"],
             lang="ur"),
        dict(title="Arz-e-Pak Advertising", headline="Reach serious buyers, not idle clicks",
             advertiser="Arz-e-Pak", category="services", slot="newsletter",
             body="Put your brand in front of verified buyers, landlords, investors and "
                  "developers across four cities — with transparent performance reporting.",
             cta_label="Request the media kit", cta_url="https://example.com/advertise",
             phone="+92 42 111 000 000", price_text="Campaigns from Rs 150,000 / month",
             priority=90, weight=1.0, status="active", budget=0,
             impressions=1_900, clicks=38, keywords=["advertise", "media kit"],
             tags=["house", "services"], lang="en"),
    ]
    for row in ads:
        row.setdefault("city_id", None)
        # Demo creatives: in-feed cards bill per click, the rest per 1,000 impressions.
        row.setdefault("sample", True)
        row.setdefault("pricing", "cpc" if row.get("slot") == "infeed" else "cpm")
        row.setdefault("rate", 25.0 if row.get("slot") == "infeed" else 400.0)
        content.ads_db.append(content.Advertisement(**row))


def _seed_construction() -> None:
    """Seed the construction wing: a nav page and a few worked cost estimates."""
    if not any(p.key == "construction" for p in content.pages_db):
        content.pages_db.append(content.PortalPage(
            key="construction", title="Construction Wing", category="services", order=60,
            nav_label="Construction", subtitle="Techniques, cost analysis, estimation & building codes",
            summary="Estimate build cost, compare techniques and follow the codes with one engine.",
            body=[
                "The construction wing turns a plot and a brief into a defensible build cost. "
                "It carries a catalogue of construction techniques — from conventional RCC frames "
                "and load-bearing masonry to steel, pre-engineered buildings, precast, tunnel "
                "formwork and ICF — each scored on cost, speed, soil and seismic suitability.",
                "A parameterised estimator builds the cost up element by element (substructure, "
                "frame, masonry, roofing, finishes, MEP and external works), then adds "
                "preliminaries, contingency, consultancy and contractor overhead & profit, and "
                "returns a phase timeline and a material take-off. Rate analysis shows the "
                "material, labour and plant split inside every BOQ line.",
                "Because construction choice is an investment decision, the wing also models the "
                "impact on real-estate value, rent and payback, and it gathers the applicable "
                "codes and byelaws (zoning, setbacks, FAR, structural, seismic, fire, "
                "accessibility, environmental) with the full NOC / approval workflow.",
            ],
            highlights=[
                {"label": "Techniques", "value": "17", "sub": "structure to green building"},
                {"label": "Quality tiers", "value": "4", "sub": "economy → luxury"},
                {"label": "Element rates", "value": "16", "sub": "material · labour · plant"},
                {"label": "Guidelines", "value": "12", "sub": "codes, byelaws & HSE"},
            ],
            bullets=[
                "Element-wise cost estimate with contingency, consultancy and margin",
                "Rate analysis and material take-off from covered area",
                "Technique comparison by cost, unit rate and build speed",
                "Impact of build quality on value, rent and payback",
                "Approval workflow and QA/HSE checklists",
            ],
            tags=["construction", "cost", "codes"],
        ))

    if construction.estimates_db:
        return
    demos = [
        ("10 Marla G+1 house — DHA Lahore", 2722.5, 2, "house", "standard", "rcc_frame", "Lahore", 5445.0),
        ("Apartment block — Bahria Karachi", 48000.0, 8, "apartment", "premium", "tunnel_form", "Karachi", None),
        ("Warehouse — Islamabad Smart City", 30000.0, 1, "warehouse", "standard", "peb", "Islamabad", None),
        ("Office floor — Lahore Smart City", 6500.0, 1, "office", "premium", "rcc_frame", "Lahore", None),
    ]
    for title, area, floors, btype, tier, system, city, plot in demos:
        est = construction.estimate_construction(area, floors=floors, building_type=btype,
                                                 quality_tier=tier, system=system, city=city,
                                                 plot_area=plot)
        if "error" not in est:
            construction.save_estimate(est, title)


def _seed_maintenance() -> None:
    """Seed the maintenance wing: a nav page, two plans and a few work orders."""
    if not any(p.key == "maintenance" for p in content.pages_db):
        content.pages_db.append(content.PortalPage(
            key="maintenance", title="Maintenance Wing", category="services", order=70,
            nav_label="Maintenance", subtitle="Services, lifecycle, condition & cost after handover",
            summary="Plan preventive maintenance, budget repairs and protect asset value.",
            body=[
                "The maintenance wing looks after a building after handover. It catalogues the "
                "maintainable components — structure, envelope, plumbing, electrical, HVAC, "
                "finishes, lifts and external works — with their expected service life, "
                "replacement cost and inspection frequency.",
                "It produces a preventive-maintenance calendar, an annual cost estimate with a "
                "category breakdown, a multi-year capital-replacement reserve study, and "
                "repair-versus-replace analysis for ageing components. A defect catalogue covers "
                "the problems Pakistani buildings actually suffer: seepage, dampness, cracks, "
                "corrosion, electrical faults and termites.",
                "Finally, it quantifies the real-estate impact of maintenance — a well-maintained "
                "asset sells and lets faster, commands a higher rent and retains tenants longer, "
                "so maintenance is treated as an investment, not a cost.",
            ],
            highlights=[
                {"label": "Components", "value": "19", "sub": "with service lives"},
                {"label": "Services", "value": "18", "sub": "trades & vendors"},
                {"label": "Defects", "value": "15", "sub": "diagnosis & repair"},
                {"label": "AMC tiers", "value": "3", "sub": "basic → comprehensive"},
            ],
            bullets=[
                "Preventive-maintenance calendar with frequencies and tasks",
                "Annual maintenance cost and capital-replacement reserve",
                "Repair-vs-replace decisions with a 5-year comparison",
                "Defect diagnosis, repair methods and prevention",
                "Impact of maintenance on value, rent, yield and occupancy",
            ],
            tags=["maintenance", "lifecycle", "services"],
        ))

    if maintenance.plans_db or maintenance.work_orders_db:
        return
    plans = [
        ("House AMC — DHA Lahore", 2722.5, "house", "standard", 6, "Lahore", "good"),
        ("Apartment tower AMC — DHA Karachi", 48000.0, "apartment", "comprehensive", 9, "Karachi", "fair"),
    ]
    for title, area, ptype, tier, age, city, band in plans:
        est = maintenance.estimate_maintenance(area, property_type=ptype, tier=tier,
                                               age_years=age, city=city)
        if "error" not in est:
            est["condition_band"] = band
            maintenance.save_plan(est, title)
    work_orders = [
        ("Roof seepage — House 12, DHA Lahore", "house", "roof_waterproofing", "roof_seepage", "urgent", 78000.0),
        ("Annual lift service — Tower B", "apartment", "lifts", "lift_fault", "soon", 55000.0),
        ("Electrical overheating — Office floor 3", "office", "electrical", "electrical_fault", "urgent", 25000.0),
        ("Interior repaint — Apartment 4C", "apartment", "interior_paint", "paint_peeling", "routine", 62000.0),
    ]
    for title, ptype, comp, defect, prio, cost in work_orders:
        maintenance.work_orders_db.append(maintenance.WorkOrder(
            title=title, property_type=ptype, component=comp, defect=defect,
            priority=prio, status="open", estimated_cost=cost))


def _seed_agentic_os() -> None:
    """Seed the agentic products: nav pages, transactions, leasing, marketing, commercial."""
    pages = [
        {"key": "agentic", "title": "Agentic OS", "category": "platform", "order": 74,
         "nav_label": "Agentic OS",
         "subtitle": "An AI agent layer over one shared data layer",
         "summary": "Buyer, seller, broker, landlord and investor agents — planned, audited, human-approved.",
         "body": [
             "The Agentic Operating System turns the portal from a search tool into an agent that "
             "understands a goal and acts on it. Product agents — a conversational homebuying agent, "
             "a seller pricing & marketing agent, a broker workspace, an investment screener, an "
             "autonomous leasing agent, a marketing conductor and two MCP products — act across the "
             "CRM, the ledger, GIS, leasing and marketing on one shared data layer.",
             "Every autonomous step is planned first, bound to a real portal tool and gated for human "
             "approval where the agent is not fully autonomous. The full run — steps, outputs and "
             "approvals — is recorded as an audit trail, so an agent's work is as traceable as a "
             "human's.",
             "Because the same tools are exposed over MCP, an external AI client (Claude, ChatGPT, "
             "Cursor) can drive the very same agents — the 'MCP for brokers' loop.",
         ],
         "highlights": [{"label": "Agents", "value": "24", "sub": "product + specialist"},
                        {"label": "Products", "value": "8", "sub": "P0–P2 roadmap"},
                        {"label": "Autonomous", "value": "8", "sub": "no human in the loop"},
                        {"label": "Audit", "value": "full", "sub": "every run recorded"}],
         "bullets": ["Plan → execute → review → deliver with approval gates",
                     "Smart Actions morning brief across the whole portal",
                     "Move-likelihood and seller-intent scoring",
                     "Multi-agent orchestration with hand-offs",
                     "MCP-first: the same tools an external AI client calls"],
         "tags": ["agentic", "ai", "automation"]},
        {"key": "transactions", "title": "Transactions", "category": "services", "order": 76,
         "nav_label": "Transactions",
         "subtitle": "The deal-to-close lifecycle, wired to the ledger",
         "summary": "Offers, contract terms, deadlines, e-signatures, commission and revenue share.",
         "body": [
             "The transaction module is the moat: it links the deal-to-close lifecycle directly to "
             "the financial ledger. A transaction carries its milestone and deadline checklist from "
             "offer acceptance through KYC, title search, due diligence, financing, signing, NOC and "
             "closing.",
             "Contract terms are extracted from agreement text, offers are negotiated and countered, "
             "e-signatures are tracked to completeness, and on close the commission and VAT are "
             "allocated across the platform, listing agent and selling agent — the balanced journal "
             "entry is posted and the payouts recorded, all in one step.",
         ],
         "highlights": [{"label": "Stages", "value": "10", "sub": "draft → closed"},
                        {"label": "Checklists", "value": "5", "sub": "sale · rental · lease · …"},
                        {"label": "Commission", "value": "auto", "sub": "split & posted"},
                        {"label": "Signatures", "value": "e-sign", "sub": "role-tracked"}],
         "bullets": ["Milestone/deadline tracking with RAG status",
                     "Contract-term extraction with confidence",
                     "Offer negotiation and counter-offers",
                     "E-signature verification by role",
                     "Commission split, ledger posting and payouts on close"],
         "tags": ["transactions", "closing", "ledger"]},
        {"key": "leasing", "title": "Autonomous Leasing", "category": "services", "order": 78,
         "nav_label": "Leasing",
         "subtitle": "24/7 inquiry handling, screening and renewals",
         "summary": "Answer tenants across every channel, screen applicants and never let below cost.",
         "body": [
             "The autonomous leasing agent holds 24/7 conversations across web chat, WhatsApp, SMS, "
             "e-mail and voice — answering availability, price, amenity, commute and schools "
             "questions and pre-screening applicants in minutes.",
             "A rent floor derived from each unit's holding cost guarantees a unit is never let at a "
             "loss. Screening weighs income-to-rent, references, a behavioural credit proxy and "
             "employment into an approve / conditional / decline decision, and the renewal agent "
             "recommends renewal rents while protecting good tenants.",
         ],
         "highlights": [{"label": "Channels", "value": "5", "sub": "web → voice"},
                        {"label": "Auto-handled", "value": "24/7", "sub": "no human touch"},
                        {"label": "Rent floor", "value": "cost +", "sub": "never at a loss"},
                        {"label": "Screening", "value": "3-band", "sub": "approve/conditional/decline"}],
         "bullets": ["Cross-channel inquiry classification and replies",
                     "Holding-cost rent floor",
                     "Application screening with conditions",
                     "Renewal rent and retention recommendations",
                     "Rent-collection board from the ledger"],
         "tags": ["leasing", "rental", "screening"]},
        {"key": "marketing", "title": "AI Marketing Conductor", "category": "services", "order": 80,
         "nav_label": "Marketing",
         "subtitle": "Lead engine · routing · re-engagement · content",
         "summary": "Capture, qualify, route and revive leads — then generate the content.",
         "body": [
             "The AI Marketing Conductor captures leads across every channel, qualifies them by "
             "channel quality, budget, timeline and engagement, and routes them by postcode, "
             "language and price to the right agent and SLA.",
             "It mines dormant and previously-lost leads for false negatives and drafts reactivation "
             "outreach, generates listing copy, social posts, reels and market reports (human-"
             "approved before publishing), and plans multichannel campaigns with budget allocation "
             "and KPIs.",
         ],
         "highlights": [{"label": "Channels", "value": "10", "sub": "referral → portal"},
                        {"label": "Bands", "value": "4", "sub": "hot → cold"},
                        {"label": "Re-engage", "value": "auto", "sub": "false negatives"},
                        {"label": "Content", "value": "6 kinds", "sub": "human-approved"}],
         "bullets": ["Cross-channel lead qualification",
                     "Rule-based routing by geography and language",
                     "Dormant-lead re-engagement and drafting",
                     "Content generation across six formats",
                     "Campaign planning with budget and KPIs"],
         "tags": ["marketing", "leads", "content"]},
        {"key": "commercial", "title": "Products & Pricing", "category": "platform", "order": 82,
         "nav_label": "Products & Pricing",
         "subtitle": "The commercial model — subscriptions, usage and performance",
         "summary": "Eight products, hybrid pricing, per-call metering, billing and revenue share.",
         "body": [
             "Commercialization turns the roadmap into revenue. The catalogue lists the eight "
             "products with their priority (P0–P2), segment and positioning, priced on a hybrid "
             "model: a subscription base plus usage-based metering (per MCP tool call or per "
             "qualified lead) plus a performance share on closings and rent.",
             "Usage is metered per account and tool, assembled into a billing statement (plan fee, "
             "overage, VAT), and performance revenue is split between the platform and partners with "
             "payables recorded against each transaction.",
         ],
         "highlights": [{"label": "Products", "value": "8", "sub": "P0–P2"},
                        {"label": "Models", "value": "5", "sub": "hybrid pricing"},
                        {"label": "Metering", "value": "per call", "sub": "usage-based"},
                        {"label": "Share", "value": "performance", "sub": "on closings"}],
         "bullets": ["Product catalogue with positioning",
                     "Subscription + usage + performance pricing",
                     "Per-call metering and usage summaries",
                     "Usage-based billing statements with VAT",
                     "Performance revenue share and payouts"],
         "tags": ["commercial", "pricing", "billing"]},
    ]
    for pg in pages:
        if not any(p.key == pg["key"] for p in content.pages_db):
            content.pages_db.append(content.PortalPage(**pg))

    # ---- Transactions ----
    if not transactions.transactions_db:
        tx1 = transactions.create_transaction(
            "sale", price=28_500_000, property_title="10 Marla House — DHA Lahore",
            buyer_name="Bilal Khan", seller_name="Ahmed Ali", start_date="2026-10-05", source="portal")
        transactions.add_offer(tx1.id, 27_000_000, buyer_name="Bilal Khan")
        transactions.add_signature(tx1.id, "Bilal Khan", role="buyer", signed=True)
        transactions.add_signature(tx1.id, "Ahmed Ali", role="seller", signed=False)
        tx2 = transactions.create_transaction(
            "rental", price=90_000, property_title="2-bed Apartment — DHA Karachi",
            buyer_name="Sara Malik", seller_name="Landlord Co", start_date="2026-10-12", source="leasing_agent")
        transactions.add_signature(tx2.id, "Sara Malik", role="tenant", signed=True)

    # ---- Leasing ----
    if not leasing.units_db:
        units = [
            ("2-bed Apartment — DHA Lahore", 90_000, "Lahore", "DHA Lahore", 2, 1100, 180_000, 70_000,
             ["lift", "backup power", "security"]),
            ("3-bed House — Bahria Karachi", 145_000, "Karachi", "Bahria Town Karachi", 3, 1800, 290_000,
             110_000, ["gated", "parking", "solar"]),
            ("Studio — Gulberg Islamabad", 55_000, "Islamabad", None, 1, 550, 110_000, 40_000,
             ["furnished", "wifi"]),
        ]
        for title, rent, city, scheme, beds, area, dep, hold, am in units:
            u = leasing.RentalUnit(title=title, rent=rent, city=city, scheme=scheme, bedrooms=beds,
                                   area=area, deposit=dep, monthly_holding_cost=hold, amenities=am)
            u.floor_rent = leasing.rent_floor(hold)["rent_floor"]
            leasing.units_db.append(u)
        leasing.handle_inquiry(leasing.units_db[0], "Is it still available? What is the rent and deposit?",
                               channel="whatsapp")
        leasing.handle_inquiry(leasing.units_db[1], "How is the commute to the city centre and are there schools nearby?",
                               channel="web_chat")
        app = leasing.Application(unit_id=leasing.units_db[0].id, applicant="Sara Malik",
                                  monthly_income=280_000, employment="salaried", references_count=2,
                                  credit_proxy=78)
        leasing.applications_db.append(app)

    # ---- Marketing ----
    if not marketing.routes_db:
        marketing.add_route("DHA Lahore · prime", {"city": "Lahore", "price_min": 20_000_000},
                            queue="prime", priority=10, sla_hours=2)
        marketing.add_route("Karachi commercial", {"city": "Karachi", "use_type": "commercial"},
                            queue="commercial", priority=20, sla_hours=4)
        marketing.add_route("Urdu-speaking buyers", {"language": "ur"}, queue="urdu_desk",
                            priority=30, sla_hours=6)
    if not marketing.campaigns_db:
        marketing.campaign_plan("Launch the Agentic OS", 500_000, ["whatsapp", "website", "instagram"],
                                days=14, audience=50_000)
    if not marketing.assets_db and properties_db:
        p0 = properties_db[0]
        marketing.generate_content("market_report",
                                   listing={"id": p0.id, "title": p0.title, "city": city_name(p0.city_id),
                                            "price": p0.price}, topic=city_name(p0.city_id))

    # ---- Commercialization ----
    if not commercial.subscriptions_db:
        commercial.subscribe("demo-brokerage", "broker_seat", seats=5)
        for tool in ("property_intelligence_mcp.gis_score", "buyer_recommend",
                     "seller_cma", "transaction_progress"):
            commercial.meter_usage("demo-brokerage", tool, units=120,
                                   product="property_intelligence_mcp")
        commercial.record_payout("TXN-1001", 570_000, "platform", 0.20, role="platform")

    # ---- Agent runs (audit trail) ----
    if not agents.runs_db:
        agents.run_agent("broker_workspace", "daily morning brief", dispatch=_agent_tool_dispatch,
                         context={}, approve=True)
        agents.run_agent("autonomous_leasing_agent", "answer overnight inquiries",
                         dispatch=_agent_tool_dispatch, context={}, approve=True)


def _seed_tools() -> None:
    """Seed the Tools & Utilities wing: a nav page and one saved example project."""
    if not any(p.key == "tools" for p in content.pages_db):
        content.pages_db.append(content.PortalPage(
            key="tools", title="Tools & Utilities", category="services", order=78,
            nav_label="Tools", subtitle="Calculators · GIS · CAD · photo · documents · calendar",
            summary="Free professional property tools: calculators, mapping, conversion and the "
                    "Pakistan & Islamic calendar.",
            body=[
                "The Tools & Utilities center turns the portal from a listings site into a "
                "working professional toolkit. It offers property and finance calculators, a "
                "plot & construction studio, GIS measurement and georeferencing, CAD/plan "
                "utilities, photo geotagging, document conversion, the Pakistan & Islamic "
                "calendar and a reports/export studio.",
                "Every tool runs on the same engine in the MCP server and the REST API, so the "
                "answers are identical whichever way you call them. Tools that genuinely need "
                "a heavy or licensed dependency (GDAL, PyMuPDF, Tesseract, DWG conversion) say "
                "so instead of pretending to do the work.",
            ],
            highlights=[
                {"label": "Calculators", "value": "12+", "sub": "finance & property"},
                {"label": "Mapping", "value": "GIS", "sub": "measure & georeference"},
                {"label": "Photo GPS", "value": "EXIF", "sub": "read & write, dependency-free"},
                {"label": "Calendar", "value": "Hijri", "sub": "Pakistan holidays + .ics"},
            ],
            bullets=[
                "Convert marla / kanal / sqft / sqm with the right standard",
                "Estimate mortgage, transfer costs, CGT and commission",
                "Measure a plot on the map or from surveyed coordinates",
                "Export GeoJSON, KML, PDF brochures and CSV",
            ],
            tags=["tools", "calculators", "gis", "calendar", "documents"],
            status="published",
        ))
    if not tools.projects_db:
        tools.save_project(
            name="Sample: 10 marla mortgage", tool="mortgage",
            inputs={"price": 10000000, "down_payment": 2000000, "annual_rate": 0.12, "years": 15},
            outputs=tools.mortgage_calculator(10000000, 2000000, 0.12, 15),
            notes="Seeded example so the Tools Center shows a recent tool.")


def _seed_pmo() -> None:
    """Seed the PMO wing: a nav page and one running example project."""
    if not any(p.key == "pmo" for p in content.pages_db):
        content.pages_db.append(content.PortalPage(
            key="pmo", title="Projects & Monitoring", category="services", order=79,
            nav_label="Projects", subtitle="Plan · schedule · track · control — in-house PMO",
            summary="Run the portal's own projects: WBS, critical path, earned value, cost and "
                    "risk control, site diaries and a live RAG dashboard.",
            body=[
                "The Projects & Monitoring (PMO) wing is the in-house project-management, "
                "monitoring and tracking system for the developments the portal itself delivers. "
                "It keeps a project register and a weighted work-breakdown, then runs a "
                "forward/backward scheduling pass over the task network to produce float, the "
                "critical path and a Gantt plan on a six-day (Mon–Sat) working week.",
                "Progress is duration-weighted and earned value follows the standard definitions "
                "(PV, EV, AC, SV, CV, SPI, CPI, EAC, ETC, VAC, TCPI), so cost and schedule "
                "performance are always visible. A monitoring layer turns that into schedule, "
                "cost, risk and quality RAG status with an exception-based alert engine and a "
                "portfolio dashboard.",
                "Around the core sit the controls a project office actually runs on: a RAID "
                "register with a probability × impact matrix, daily site diaries, variation "
                "requests with cost and schedule impact, stage inspections scored into a quality "
                "index, meeting action items, resource loading and full status reports as JSON "
                "or printable HTML.",
            ],
            highlights=[
                {"label": "Projects", "value": "Register", "sub": "portfolio dashboard"},
                {"label": "Scheduling", "value": "CPM", "sub": "float + critical path"},
                {"label": "Control", "value": "EVM", "sub": "SPI · CPI · EAC"},
                {"label": "Monitoring", "value": "RAG", "sub": "alerts & KPIs"},
            ],
            bullets=[
                "Project register with budget, dates, sponsor and manager",
                "Critical-path scheduling and Gantt structure",
                "Earned value, S-curve and cost control",
                "RAID register, site diary, variations and inspections",
                "Health RAG, alerts and portfolio dashboard",
            ],
            tags=["projects", "pmo", "monitoring", "scheduling", "earned-value"],
            status="published",
        ))

    if pmo.projects_db:
        return
    res = pmo.create_project(
        "Gulberg Heights — 24 Apartments", project_type="construction", city="Lahore",
        scheme="Gulberg Greens", client="Al-Faisal Developers", description="G+7 residential block, 24 units.",
        start_date="2026-01-05", end_date="2026-12-31", budget=480_000_000,
        contract_value=560_000_000, priority="high", status="active",
    )
    pid = res["project"]["id"]
    pmo.update_project(pid, baseline_end="2026-12-31", notes="Demo project seeded by the portal.")

    pm = pmo.add_resource("Engr. Bilal Ahmed", role="project_manager", day_rate=30000)["resource"]
    se = pmo.add_resource("Engr. Sana Khan", role="site_engineer", day_rate=18000)["resource"]
    mason = pmo.add_resource("Rashid & crew", role="foreman", trade="masonry", day_rate=9500,
                             capacity_pct=100)["resource"]
    pmo.add_resource("Imran Steel Fixers", role="subcontractor", trade="steel", day_rate=0,
                     capacity_pct=100)
    pmo.update_project(pid, manager_id=pm["id"])

    tasks = pmo.tasks_for(pid)
    if tasks:
        pmo.assign(tasks[0].id, pm["id"], units_pct=60)
        pmo.assign(tasks[6].id, se["id"], units_pct=80)
        pmo.assign(tasks[8].id, se["id"], units_pct=40)
        pmo.assign(tasks[9].id, mason["id"], units_pct=100)
        # Progress is driven by the plan so the demo shows a credible S-curve.
        today = pmo._today().isoformat()
        upcoming = 0
        for row in pmo.build_schedule(pid)["tasks"]:
            if row["planned_finish"] < today:
                pmo.update_task(row["id"], progress_pct=100, status="done",
                                actual_start=row["planned_start"], actual_finish=row["planned_finish"])
            elif upcoming < 2:
                pmo.update_task(row["id"], progress_pct=40, status="in_progress",
                                actual_start=row["planned_start"])
                upcoming += 1

    pmo.add_cost(pid, 92_000_000, category="substructure", description="Foundation & raft",
                 kind="actual", vendor="Sirbuland Contractors")
    pmo.add_cost(pid, 250_000_000, category="structure", description="RCC frame, all floors",
                 kind="actual", vendor="Sirbuland Contractors")
    pmo.add_cost(pid, 100_000_000, category="mep", description="MEP rough-in & services",
                 kind="actual", vendor="Zeeshan Electro-Mechanical")
    pmo.add_cost(pid, 34_000_000, category="finishes", description="Finishes package PO",
                 kind="committed", vendor="Master Tiles & Sanitary")
    pmo.record_progress(pid, 34.0, note="Frame to 4th floor slab cast", by="Engr. Bilal Ahmed",
                        manpower=68, weather="Dry, 32°C")

    pmo.add_risk(pid, "Steel price escalation", probability=4, impact=4, category="cost",
                 owner="Engr. Bilal Ahmed", mitigation="Lock monthly rates with the supplier.",
                 due_on="2026-05-30")
    pmo.add_risk(pid, "Monsoon delays to external works", probability=3, impact=3,
                 category="weather", owner="Engr. Sana Khan",
                 mitigation="Front-load external drainage before June.")
    pmo.add_risk(pid, "Approval of revised façade", probability=2, impact=4, kind="issue",
                 category="approvals", owner="Design team")

    pmo.log_site_day(pid, date="2026-06-15", weather="Clear, 38°C", manpower=68,
                     equipment=["Tower crane", "Concrete pump", "Excavator"],
                     work_done="5th-floor slab shuttering and steel fixing; column kickers cast.",
                     issues="Cement delivery delayed by 3 hours.", safety_incidents=0,
                     visitors="Client consultant", by="Engr. Sana Khan")

    pmo.raise_change(pid, "Add basement car-parking", description="Client request for 18 extra bays.",
                     reason="Buyer demand", cost_impact=41_000_000, schedule_impact_days=35,
                     requested_by="Al-Faisal Developers", status="submitted")

    pmo.add_inspection(pid, "5th-floor frame inspection", phase_key="superstructure",
                       area="structural_frame", inspector="Engr. Sana Khan", checklist=[
                           {"item": "Concrete grade as per design", "result": "pass"},
                           {"item": "Reinforcement cover & spacing", "result": "fail",
                            "note": "Cover blocks missing at 3 columns"},
                           {"item": "Shuttering tightness & alignment", "result": "pass"},
                           {"item": "Curing arrangement", "result": "pass"},
                       ])
    pmo.add_action(pid, "Fix cover blocks and re-inspect 5th floor", owner="Engr. Sana Khan",
                   due_on="2026-06-25", priority="high", meeting="Weekly site meeting")


def _seed_messaging() -> None:
    """Seed the team-messaging wing: profiles, channels, a DM and a property discussion."""
    if not any(p.key == "messaging" for p in content.pages_db):
        content.pages_db.append(content.PortalPage(
            key="messaging", title="Team Messaging", category="services", order=80,
            nav_label="Messages",
            subtitle="Conversations tied to properties, plans, customers and tasks",
            summary="An internal team workspace: direct messages, team channels and a discussion "
                    "panel on every property record, with e-mail and optional Telegram alerts.",
            body=[
                "The Team Messaging wing is the portal's internal communication system. It keeps the "
                "team's conversations inside Arz-e-Pak and tied to the work itself: direct messages, "
                "group discussions and channels such as Sales, Property Verification, GIS & Mapping, "
                "Customer Support and Management, plus an internal discussion panel on every "
                "property record so a listing, its map, its documents and its follow-up tasks stay "
                "in one place.",
                "Messages support threaded replies, @mentions, pins, reactions, search, unread "
                "counts and read receipts. Files are shared as references — a controlled storage key "
                "or a link to an existing portal record — and handed out through permission-checked, "
                "expiring links, so large plans and PDFs never sit inside chat text.",
                "Any message can be turned into a tracked action: a task, an approval, a property "
                "verification or a follow-up, with an owner and a deadline. A notification queue "
                "with per-user, per-category preferences (in-app, e-mail and optional Telegram) keeps "
                "everyone informed without making e-mail or Telegram the system of record; Telegram "
                "alerts carry only short text and an authenticated deep link, never confidential "
                "documents.",
            ],
            highlights=[
                {"label": "Chat", "value": "Internal", "sub": "DMs · channels · property threads"},
                {"label": "Actions", "value": "Message→task", "sub": "owner + deadline"},
                {"label": "Alerts", "value": "In-app · e-mail", "sub": "Telegram optional"},
                {"label": "Control", "value": "Audit", "sub": "roles · retention · moderation"},
            ],
            bullets=[
                "Direct messages, group discussions and named team channels",
                "A property-linked discussion panel on every listing",
                "Mentions, replies, pins, search, unread counts and read receipts",
                "Permission-checked, expiring file links — files stay in controlled storage",
                "Message → task / approval / verification with owner and deadline",
                "Notification queue with preferences, quiet hours and an outbox",
                "Optional Telegram bot for alerts (short text + deep link only)",
                "Roles, audit trail, access revocation and retention policy",
            ],
            tags=["messaging", "chat", "notifications", "telegram", "email", "collaboration"],
            status="published",
        ))

    if messaging.profiles_db:
        return

    team: List[Dict[str, Any]] = []
    for u in auth.users_db:
        if u.status not in ("active", "pending"):
            continue
        team.append({
            "user_id": u.id, "display_name": u.name or (u.email or u.id),
            "role": u.role or "member", "email": u.email, "mobile": u.mobile,
            "title": (u.roles[0] if u.roles else None),
        })
    if not team:
        team = [
            {"user_id": "team_admin", "display_name": "Ayesha Khan", "role": "admin",
             "email": "admin@portal.pk", "handle": "ayesha"},
            {"user_id": "team_agent", "display_name": "Bilal Ahmed", "role": "agent",
             "email": "agent@portal.pk", "handle": "bilal"},
            {"user_id": "team_gis", "display_name": "Sana Tariq", "role": "member",
             "email": "gis@portal.pk", "handle": "sana"},
        ]

    property_ids = [p.id for p in properties_db[:3]]
    messaging.seed_demo(team, property_ids=property_ids)

    admin = next((t["user_id"] for t in team if t["role"] in messaging.ADMIN_ROLES),
                 team[0]["user_id"])
    others = [t["user_id"] for t in team if t["user_id"] != admin]
    sales = next((c for c in messaging.conversations_db if c.channel_key == "sales"), None)
    if sales and others:
        messaging.create_action(sales.id, admin, "Prepare the DHA Phase 6 rate list",
                                kind="task", owner_id=others[0], due_on="2026-07-05",
                                detail="Prices per marla for 5 and 10 marla files.", announce=False)
        messaging.create_action(sales.id, admin, "Approve the new listing banner",
                                kind="approval", owner_id=others[0], announce=False)
    if others:
        messaging.telegram_link(others[0], "100200300", username="arzteam",
                                categories=["mention", "direct", "lead", "approval"])
        owner = messaging.find_profile(others[0])
        if owner:
            owner.presence = "online"
        messaging.queue_notification(
            others[0], "lead", title="Three new leads need attention",
            body="Gulberg Greens and DHA enquiries are waiting for first response.",
            priority="high",
        )
        messaging.queue_notification(
            others[0], "approval", title="Property verification requires approval",
            body="Title documents for the Gulberg Greens listing are ready for review.",
            priority="high",
        )
    messaging.dispatch_pending(force=True)


def init_sample_data() -> None:
    """Populate the in-memory stores with a realistic Pakistani dataset."""
    # ---- Cities ----
    lahore = City(name="Lahore", state="Punjab", latitude=31.5204, longitude=74.3587, description="Cultural heart of Pakistan.")
    karachi = City(name="Karachi", state="Sindh", latitude=24.8607, longitude=67.0011, description="Financial capital and largest city.")
    islamabad = City(name="Islamabad", state="Islamabad Capital Territory", latitude=33.6844, longitude=73.0479, description="Planned capital city.")
    rawalpindi = City(name="Rawalpindi", state="Punjab", latitude=33.5651, longitude=73.0169, description="Twin city of Islamabad.")
    cities_db.extend([lahore, karachi, islamabad, rawalpindi])

    # ---- Schemes ----
    lsc = HousingScheme(name="Lahore Smart City", city_id=lahore.id, total_units=5000, established_year=2020, developer="Future Holdings", latitude=31.4504, longitude=74.2800)
    garden = HousingScheme(name="Garden Town", city_id=lahore.id, total_units=200, established_year=1995, developer="LDA")
    dha_lhr = HousingScheme(name="DHA Lahore", city_id=lahore.id, total_units=8000, established_year=1975, developer="DHA")
    bahria_lhr = HousingScheme(name="Bahria Town Lahore", city_id=lahore.id, total_units=12000, established_year=2000, developer="Bahria Town")
    dha_khi = HousingScheme(name="DHA Karachi", city_id=karachi.id, total_units=6000, established_year=1990, developer="DHA")
    bahria_khi = HousingScheme(name="Bahria Town Karachi", city_id=karachi.id, total_units=10000, established_year=2014, developer="Bahria Town")
    isb_sc = HousingScheme(name="Islamabad Smart City", city_id=islamabad.id, total_units=3000, established_year=2015, developer="Future Holdings")
    dha_isb = HousingScheme(name="DHA Islamabad", city_id=islamabad.id, total_units=7000, established_year=1996, developer="DHA")
    gulberg = HousingScheme(name="Gulberg Greens", city_id=islamabad.id, total_units=4000, established_year=2008, developer="Gulberg")
    housing_schemes_db.extend([lsc, garden, dha_lhr, bahria_lhr, dha_khi, bahria_khi, isb_sc, dha_isb, gulberg])

    # ---- Blocks / zones ----
    blocks = [
        BlockZoneArea(name="Sector A", scheme_id=lsc.id, area_type="residential"),
        BlockZoneArea(name="Sector B", scheme_id=lsc.id, area_type="residential"),
        BlockZoneArea(name="Commercial Downtown", scheme_id=lsc.id, area_type="commercial"),
        BlockZoneArea(name="Old Garden", scheme_id=garden.id, area_type="residential"),
        BlockZoneArea(name="New Garden", scheme_id=garden.id, area_type="residential"),
        BlockZoneArea(name="Phase 6", scheme_id=dha_lhr.id, area_type="residential"),
        BlockZoneArea(name="Phase 8 Commercial", scheme_id=dha_lhr.id, area_type="commercial"),
        BlockZoneArea(name="Sector C", scheme_id=bahria_lhr.id, area_type="residential"),
        BlockZoneArea(name="Luxury Villas", scheme_id=dha_khi.id, area_type="luxury"),
        BlockZoneArea(name="Precinct 10", scheme_id=bahria_khi.id, area_type="residential"),
        BlockZoneArea(name="Residential Area", scheme_id=isb_sc.id, area_type="residential"),
        BlockZoneArea(name="Sector F", scheme_id=dha_isb.id, area_type="residential"),
        BlockZoneArea(name="Executive Block", scheme_id=gulberg.id, area_type="commercial"),
    ]
    block_zone_areas_db.extend(blocks)

    def prop(**kw) -> Property:
        p = Property(**kw)
        derive_areas(p)
        properties_db.append(p)
        return p

    # ---- Properties (16) ----
    prop(
        title="Modern 10 Marla House",
        description="Brand-new 5-bed house in a gated community with a basement and solar system.",
        amenities=["Gated community", "Basement", "Solar system"],
        price=45_000_000, use_type="residential", category="house",
        marla_area=10, bedrooms=5, bathrooms=6, floors=2, featured=True,
        city_id=lahore.id, scheme_id=lsc.id, block_zone_area_id=blocks[0].id,
        latitude=31.4504, longitude=74.2810, street_address="Main Boulevard", sector="A", agent_id="",
    )
    prop(
        title="1 Kanal Corner House",
        description="1 kanal corner house with a large lawn in DHA Phase 6.",
        amenities=["Corner plot", "Large lawn"],
        price=95_000_000, use_type="residential", category="house",
        kanal_area=1, bedrooms=6, bathrooms=7, floors=2, featured=True,
        city_id=lahore.id, scheme_id=dha_lhr.id, block_zone_area_id=blocks[5].id,
        latitude=31.4690, longitude=74.4120, street_address="Street 12", sector="Phase 6",
    )
    prop(
        title="Luxury Sea-View Apartment",
        description="4-bedroom sea-facing apartment with a gym and rooftop pool.",
        amenities=["Sea view", "Gym", "Rooftop pool"],
        price=55_000_000, use_type="residential", category="apartment",
        total_area=2600, bedrooms=4, bathrooms=4,
        city_id=karachi.id, scheme_id=dha_khi.id, block_zone_area_id=blocks[8].id,
        latitude=24.8138, longitude=67.0300, street_address="Sea View Road",
    )
    prop(
        title="Ground Floor Commercial Shop",
        description="Corner shop on a high-footfall commercial road, ideal for retail.",
        amenities=["Corner", "Main road"],
        price=15_000_000, use_type="commercial", category="shop",
        marla_area=2, city_id=lahore.id, scheme_id=lsc.id, block_zone_area_id=blocks[2].id,
        latitude=31.4480, longitude=74.2790, street_address="M.M. Alam Road",
    )
    prop(
        title="10 Marla Residential Plot",
        description="Possession-ready 10 marla plot in a developed block.",
        amenities=["Possession ready", "Developed block"],
        price=20_000_000, use_type="residential", category="plot",
        marla_area=10, city_id=lahore.id, scheme_id=garden.id, block_zone_area_id=blocks[3].id,
        latitude=31.5025, longitude=74.3379, plot_number="412",
    )
    prop(
        title="3,000 sqft Corporate Office",
        description="Fitted office floor in a Grade-A tower with parking.",
        amenities=["Fitted", "Parking"],
        price=50_000_000, use_type="commercial", category="office",
        total_area=3000, city_id=lahore.id, latitude=31.5400, longitude=74.3700,
        street_address="Main Boulevard Gulberg",
    )
    prop(
        title="5 Kanal Farmhouse",
        description="Farmhouse with orchard and swimming pool on the Islamabad outskirts.",
        amenities=["Orchard", "Swimming pool"],
        price=85_000_000, use_type="residential", category="house",
        kanal_area=5, bedrooms=5, bathrooms=5, floors=1, featured=True,
        city_id=islamabad.id, latitude=33.7000, longitude=73.1500, street_address="Murree Road",
    )
    prop(
        title="4-Bedroom Cantt House",
        description="Well-maintained 4-bedroom house close to the Cantonment.",
        price=65_000_000, use_type="residential", category="house",
        total_area=2200, marla_area=8, bedrooms=4, bathrooms=3, floors=2,
        city_id=karachi.id, latitude=24.8800, longitude=67.0500, street_address="Defence Housing Area",
    )
    prop(
        title="2 Kanal Development Plot",
        description="2 kanal plot on the main boulevard, suitable for a commercial building.",
        price=180_000_000, use_type="mix", category="plot",
        kanal_area=2, city_id=lahore.id, latitude=31.4450, longitude=74.4000,
    )
    prop(
        title="Modern 2-Bed Apartment",
        description="Compact apartment in DHA Islamabad, close to offices and schools.",
        price=45_000_000, use_type="residential", category="apartment",
        total_area=1300, bedrooms=2, bathrooms=2,
        city_id=islamabad.id, scheme_id=dha_isb.id, block_zone_area_id=blocks[11].id,
        latitude=33.6800, longitude=73.0400, street_address="DHA Islamabad",
    )
    prop(
        title="Islamabad Smart City 5 Marla House",
        description="Affordable 3-bed house in a new smart city development.",
        price=22_000_000, use_type="residential", category="house",
        marla_area=5, bedrooms=3, bathrooms=3, floors=1,
        city_id=islamabad.id, scheme_id=isb_sc.id, block_zone_area_id=blocks[10].id,
        latitude=33.6600, longitude=73.0600,
    )
    prop(
        title="Gulberg Office Floor",
        description="Executive-block office floor available for rent or sale.",
        price=38_000_000, use_type="commercial", category="floor",
        total_area=2400, city_id=islamabad.id, scheme_id=gulberg.id, block_zone_area_id=blocks[12].id,
        latitude=33.5800, longitude=73.1400,
    )
    prop(
        title="Bahria Karachi Villa",
        description="3-bed villa in a secure gated precinct.",
        amenities=["Gated community", "Security"],
        price=52_000_000, use_type="residential", category="house",
        total_area=1800, marla_area=7, bedrooms=3, bathrooms=4, floors=2,
        city_id=karachi.id, scheme_id=bahria_khi.id, block_zone_area_id=blocks[9].id,
        latitude=25.0200, longitude=67.3000,
    )
    prop(
        title="Small Retail Space",
        description="Compact retail space near a main entrance.",
        price=9_000_000, use_type="commercial", category="space",
        total_area=600, city_id=karachi.id, latitude=24.8300, longitude=67.0400,
    )
    prop(
        title="Employee Apartment Building",
        description="Multi-floor apartment building producing rental income.",
        price=120_000_000, use_type="mix", category="building",
        total_area=9000, floors=5, bedrooms=12, bathrooms=12,
        city_id=karachi.id, latitude=24.8900, longitude=67.0800,
    )
    prop(
        title="Rawalpindi 7 Marla House",
        description="Family house close to the Islamabad Expressway.",
        price=28_000_000, use_type="residential", category="house",
        marla_area=7, bedrooms=4, bathrooms=4, floors=2,
        city_id=rawalpindi.id, latitude=33.5651, longitude=73.0169,
    )

    # ---- Big projects ----
    big_projects_db.extend(
        [
            BigProject(
                name="Grand Arena Mall", city_id=lahore.id, scheme_id=lsc.id,
                project_type=PROJECT_TYPE_MALL, status="under_construction", floor_count=5,
                total_area=750_000, total_units=320, occupancy_rate=0.0, developer="Arena Holdings",
                latitude=31.4700, longitude=74.3000, start_date="2023-01-01", completion_date="2026-12-31",
                total_parking_spaces=1500, total_retail_space=500_000, total_office_space=120_000,
                amenities=["Cinema", "Food Court", "Kids Zone", "Hypermarket"],
                image_library=["https://cdn.example.com/grand-arena-mall.jpg"],
            ),
            BigProject(
                name="Serene Heights Towers", city_id=karachi.id, scheme_id=dha_khi.id,
                project_type=PROJECT_TYPE_TOWER, status="completed", floor_count=25,
                total_area=420_000, total_units=240, occupancy_rate=0.82, developer="Serene Group",
                latitude=24.8100, longitude=67.0400, completion_date="2022-06-30",
                total_residential_units=240, total_parking_spaces=500,
            ),
            BigProject(
                name="Capital Mixed-Use Plaza", city_id=islamabad.id, scheme_id=dha_isb.id,
                project_type=PROJECT_TYPE_MIXED_USE, status="completed", floor_count=12,
                total_area=300_000, total_units=180, occupancy_rate=0.74, developer="Capital Builders",
                latitude=33.6750, longitude=73.0350, completion_date="2023-03-15",
            ),
            BigProject(
                name="Green Valley Compound Housing", city_id=lahore.id, scheme_id=bahria_lhr.id,
                project_type=PROJECT_TYPE_COMPOUND_LIVING, status="under_construction", floor_count=3,
                total_area=900_000, total_units=450, occupancy_rate=0.35, developer="Bahria Town",
                latitude=31.3500, longitude=74.2200,
                amenities=["Community Pool", "Club House", "Jogging Track"],
            ),
            BigProject(
                name="Tech Corridor Office Complex", city_id=islamabad.id,
                project_type=PROJECT_TYPE_OFFICE_COMPLEX, status="planned", floor_count=8,
                total_area=260_000, total_units=120, developer="TechCorp Estates",
                latitude=33.6900, longitude=73.0700,
            ),
            BigProject(
                name="Riverside Plaza", city_id=karachi.id,
                project_type=PROJECT_TYPE_PLAZA, status="completed", floor_count=6,
                total_area=150_000, total_units=90, occupancy_rate=0.9, developer="Riverside Developers",
                latitude=24.8700, longitude=67.0200,
            ),
        ]
    )

    # ---- CRM: agents ----
    ayesha = Agent(name="Ayesha Khan", email="ayesha@realestate.pk", phone="+92-300-1111111", region="Lahore", specialization="residential", rating=4.7, deals_closed=32)
    bilal = Agent(name="Bilal Ahmed", email="bilal@realestate.pk", phone="+92-301-2222222", region="Karachi", specialization="commercial", rating=4.5, deals_closed=21, commission_rate=0.025)
    sara = Agent(name="Sara Malik", email="sara@realestate.pk", phone="+92-302-3333333", region="Islamabad", specialization="investment", rating=4.9, deals_closed=48)
    agents_db.extend([ayesha, bilal, sara])

    # ---- CRM: leads ----
    lead1 = Lead(
        name="Hassan Raza", email="hassan@example.com", phone="+92-321-4444444", source="website",
        interest_use_type="residential", interest_category="house", budget_min=30_000_000,
        budget_max=60_000_000, city_id=lahore.id, scheme_id=lsc.id, assigned_agent_id=ayesha.id,
        notes="Wants a basement and solar system.",
    )
    lead2 = Lead(
        name="Fatima Noor", email="fatima@example.com", phone="+92-333-5555555", source="referral",
        interest_use_type="commercial", interest_category="shop", budget_min=10_000_000,
        budget_max=20_000_000, city_id=lahore.id, assigned_agent_id=bilal.id,
    )
    lead3 = Lead(
        name="Usman Tariq", phone="+92-345-6666666", source="walk_in",
        interest_use_type="residential", interest_category="apartment", budget_max=50_000_000,
        city_id=islamabad.id, assigned_agent_id=sara.id,
    )
    lead4 = Lead(name="Zara Sheikh", email="zara@example.com", phone="+92-311-7777777", source="call", city_id=karachi.id)
    for l in (lead1, lead2, lead3, lead4):
        l.score = _score_lead(l)
    leads_db.extend([lead1, lead2, lead3, lead4])

    # ---- CRM: customers ----
    cust1 = Customer(name="Imran Yousaf", email="imran@example.com", phone="+92-300-8888888", type="investor", city_id=lahore.id, assigned_agent_id=sara.id)
    customers_db.append(cust1)

    # ---- CRM: interactions ----
    interactions_db.extend(
        [
            Interaction(entity_type="lead", entity_id=lead1.id, channel="call", direction="outbound", summary="Intro call; shared 3 options.", agent_id=ayesha.id),
            Interaction(entity_type="lead", entity_id=lead1.id, channel="site_visit", direction="outbound", summary="Visited Smart City house.", agent_id=ayesha.id),
            Interaction(entity_type="customer", entity_id=cust1.id, channel="meeting", direction="inbound", summary="Discussed investment portfolio.", agent_id=sara.id),
        ]
    )

    # ---- CRM: deals ----
    deals_db.extend(
        [
            Deal(title="Hassan — Smart City house", lead_id=lead1.id, property_id=properties_db[0].id, agent_id=ayesha.id, amount=45_000_000, stage="negotiation", probability=60, expected_close_date="2026-11-30"),
            Deal(title="Fatima — commercial shop", lead_id=lead2.id, property_id=properties_db[3].id, agent_id=bilal.id, amount=15_000_000, stage="proposal", probability=40),
            Deal(title="Imran — investment plot", customer_id=cust1.id, agent_id=sara.id, amount=180_000_000, stage="prospecting", probability=20),
        ]
    )
    for d in deals_db:
        a = _find_agent(d.agent_id)
        d.commission = round(d.amount * a.commission_rate, 2) if a else 0.0

    # ---- CRM: tasks ----
    soon = (datetime.now() + timedelta(days=2)).date().isoformat()
    tasks_db.extend(
        [
            Task(title="Follow up with Hassan on negotiation", assigned_agent_id=ayesha.id, related_type="lead", related_id=lead1.id, due_date=soon, priority="high"),
            Task(title="Send shop documents to Fatima", assigned_agent_id=bilal.id, related_type="deal", related_id=deals_db[1].id, due_date=soon, priority="medium"),
            Task(title="Prepare investment report for Imran", assigned_agent_id=sara.id, related_type="customer", related_id=cust1.id, priority="urgent"),
        ]
    )

    # ---- CRM: appointments ----
    appt = (datetime.now() + timedelta(days=1)).replace(microsecond=0).isoformat()
    appointments_db.extend(
        [
            Appointment(title="Site visit — Smart City house", lead_id=lead1.id, property_id=properties_db[0].id, agent_id=ayesha.id, scheduled_at=appt),
            Appointment(title="Office tour — Gulberg", lead_id=lead3.id, property_id=properties_db[11].id, agent_id=sara.id, scheduled_at=appt),
        ]
    )

    # ---- GIS: base-map ready layers (master plans, boundaries, zones) ----
    gis.add_layer(
        gis.GeoLayer(
            name="Lahore Smart City — Master Plan",
            layer_type="master_plan",
            entity_type="scheme",
            entity_id=lsc.id,
            description="Approved layout plan, rectified to real-world coordinates.",
            geojson=gis.feature_collection(
                [
                    gis.polygon_feature(
                        [[31.4460, 74.2740], [31.4460, 74.2870], [31.4560, 74.2870], [31.4560, 74.2740]],
                        {"name": "Lahore Smart City", "description": "Master plan footprint"},
                    )
                ]
            ),
            base_map="google_hybrid",
            image_url="/media/masterplans/lahore-smart-city.png",
            source_url="/media/masterplans/lahore-smart-city.pdf",
            style={"color": "#e6194b", "fillColor": "#e6194b", "fillOpacity": 0.12, "weight": 3, "opacity": 0.95},
            z_index=1,
        )
    )
    gis.add_layer(
        gis.GeoLayer(
            name="Commercial Downtown — Zone",
            layer_type="zone",
            entity_type="block",
            entity_id=blocks[2].id,
            description="Commercial zone master plan.",
            geojson=gis.feature_collection(
                [
                    gis.polygon_feature(
                        [[31.4510, 74.2800], [31.4510, 74.2825], [31.4525, 74.2825], [31.4525, 74.2800]],
                        {"name": "Commercial Downtown", "zone_type": "commercial"},
                    )
                ]
            ),
            base_map="google_satellite",
            style={"color": "#ff7f0e", "fillColor": "#ff7f0e", "fillOpacity": 0.3, "weight": 2, "opacity": 0.9},
            z_index=3,
        )
    )
    gis.add_layer(
        gis.GeoLayer(
            name="Sector A — Plot Layout",
            layer_type="plot_layout",
            entity_type="block",
            entity_id=blocks[0].id,
            description="Residential plot layout grid.",
            geojson=gis.feature_collection(
                [
                    gis.polygon_feature(
                        [[31.4470, 74.2755], [31.4470, 74.2795], [31.4495, 74.2795], [31.4495, 74.2755]],
                        {"name": "Sector A residential"},
                    )
                ]
            ),
            base_map="google_hybrid",
            style={"color": "#2ca02c", "fillColor": "#2ca02c", "fillOpacity": 0.2, "weight": 1, "opacity": 0.9},
            z_index=2,
        )
    )
    gis.add_layer(
        gis.GeoLayer(
            name="DHA Lahore — Society Boundary",
            layer_type="boundary",
            entity_type="scheme",
            entity_id=dha_lhr.id,
            description="Outer boundary of DHA Lahore phases.",
            geojson=gis.feature_collection(
                [
                    gis.polygon_feature(
                        [
                            [31.4650, 74.3950],
                            [31.4650, 74.4750],
                            [31.5200, 74.4750],
                            [31.5200, 74.3950],
                        ],
                        {"name": "DHA Lahore"},
                    )
                ]
            ),
            base_map="google_satellite",
            style={"color": "#2b8cbe", "fillColor": "#2b8cbe", "fillOpacity": 0.1, "weight": 3, "opacity": 0.9},
            z_index=1,
        )
    )
    gis.add_layer(
        gis.GeoLayer(
            name="Islamabad Smart City — Master Plan",
            layer_type="master_plan",
            entity_type="scheme",
            entity_id=isb_sc.id,
            description="Layout plan (rectified raster).",
            geojson=gis.feature_collection(
                [
                    gis.polygon_feature(
                        [[33.5150, 73.0450], [33.5150, 73.0650], [33.5300, 73.0650], [33.5300, 73.0450]],
                        {"name": "Islamabad Smart City"},
                    )
                ]
            ),
            base_map="google_hybrid",
            image_url="/media/masterplans/islamabad-smart-city.png",
            source_url="/media/masterplans/islamabad-smart-city.pdf",
            style={"color": "#9467bd", "fillColor": "#9467bd", "fillOpacity": 0.15, "weight": 3, "opacity": 0.95},
            z_index=1,
        )
    )
    gis.add_layer(
        gis.GeoLayer(
            name="Bahria Town Karachi — Master Plan",
            layer_type="master_plan",
            entity_type="scheme",
            entity_id=bahria_khi.id,
            description="Master plan footprint (rectified raster).",
            geojson=gis.feature_collection(
                [
                    gis.polygon_feature(
                        [[25.0000, 67.3000], [25.0000, 67.3500], [25.0500, 67.3500], [25.0500, 67.3000]],
                        {"name": "Bahria Town Karachi"},
                    )
                ]
            ),
            base_map="esri_world_imagery",
            image_url="/media/masterplans/bahria-town-karachi.png",
            style={"color": "#17becf", "fillColor": "#17becf", "fillOpacity": 0.12, "weight": 3, "opacity": 0.95},
            z_index=1,
        )
    )
    gis.add_layer(
        gis.GeoLayer(
            name="Lahore Smart City — Main Boulevard",
            layer_type="road",
            entity_type="scheme",
            entity_id=lsc.id,
            description="Primary access boulevard centre-line.",
            geojson=gis.feature_collection(
                [
                    gis.line_feature(
                        [[31.4470, 74.2745], [31.4500, 74.2805], [31.4555, 74.2860]],
                        {"name": "Main Boulevard"},
                    )
                ]
            ),
            base_map="google_hybrid",
            style={"color": "#f1c40f", "fillColor": "#f1c40f", "fillOpacity": 0.0, "weight": 4, "opacity": 0.95},
            z_index=5,
        )
    )

    # ---- Market intelligence: factor scores ----
    factors_db.extend(
        [
            MarketFactor(
                scope_type="national", scope_id="PK",
                development_score=66, infrastructure_score=55, economic_score=58, social_score=68,
                political_score=52, regulatory_score=54, demand_score=63,
                notes="National outlook: strong urbanisation and overseas demand, tempered by political and regulatory volatility.",
            ),
            MarketFactor(
                scope_type="city", scope_id=lahore.id,
                development_score=78, infrastructure_score=66, economic_score=64, social_score=74,
                political_score=55, regulatory_score=58, demand_score=76,
                notes="Lahore: heavy scheme pipeline (Smart City, Bahria, DHA), strong demographic pull.",
            ),
            MarketFactor(
                scope_type="city", scope_id=karachi.id,
                development_score=72, infrastructure_score=58, economic_score=68, social_score=71,
                political_score=48, regulatory_score=52, demand_score=70,
                notes="Karachi: economic hub with strong commercial demand; municipal and political risk elevated.",
            ),
            MarketFactor(
                scope_type="city", scope_id=islamabad.id,
                development_score=70, infrastructure_score=74, economic_score=70, social_score=72,
                political_score=62, regulatory_score=66, demand_score=72,
                notes="Islamabad: best governance and infrastructure scores; premium valuations.",
            ),
            MarketFactor(
                scope_type="city", scope_id=rawalpindi.id,
                development_score=64, infrastructure_score=60, economic_score=60, social_score=66,
                political_score=56, regulatory_score=55, demand_score=64,
                notes="Rawalpindi: spillover demand from Islamabad; ring-road driven upside.",
            ),
            MarketFactor(
                scope_type="scheme", scope_id=lsc.id,
                development_score=82, infrastructure_score=70, economic_score=66, social_score=76,
                political_score=58, regulatory_score=60, demand_score=80,
                notes="Lahore Smart City: flagship new society, phased delivery, investor-heavy demand.",
            ),
            MarketFactor(
                scope_type="scheme", scope_id=isb_sc.id,
                development_score=76, infrastructure_score=72, economic_score=68, social_score=72,
                political_score=60, regulatory_score=64, demand_score=74,
                notes="Islamabad Smart City: well-located, strong end-user demand.",
            ),
            MarketFactor(
                scope_type="scheme", scope_id=dha_lhr.id,
                development_score=88, infrastructure_score=84, economic_score=72, social_score=80,
                political_score=64, regulatory_score=78, demand_score=84,
                notes="DHA Lahore: mature, high-liquidity, low regulatory risk.",
            ),
            MarketFactor(
                scope_type="scheme", scope_id=bahria_khi.id,
                development_score=74, infrastructure_score=66, economic_score=64, social_score=70,
                political_score=52, regulatory_score=58, demand_score=72,
                notes="Bahria Town Karachi: large master plan; litigation and utility risk noted.",
            ),
        ]
    )

    # ---- Market intelligence: news ticker items ----
    def _ago(days: int) -> datetime:
        return datetime.now() - timedelta(days=days)

    news_db.extend(
        [
            NewsItem(
                title="SBP cuts policy rate by 100bps to 11.0% — borrowing costs fall for home finance",
                source="State Bank of Pakistan", channel_type="regulator", category="macro",
                sentiment="positive", impact_score=55, published_at=_ago(4),
                summary="Lower policy rate reduces mortgage pricing and revives end-user demand.",
                tags=["interest-rate", "mortgage"], url="https://www.sbp.org.pk/",
            ),
            NewsItem(
                title="FBR clarifies capital gains tax on property; holding-period slabs simplified",
                source="Business Recorder", channel_type="news", category="policy",
                sentiment="neutral", impact_score=10, published_at=_ago(9),
                summary="Clarity on CGT reduces transaction uncertainty for investors.",
                tags=["tax", "cgt"],
            ),
            NewsItem(
                title="LDA approves Lahore Smart City layout extension; NOC issued for two new sectors",
                source="LDA", channel_type="regulator", category="regulation",
                sentiment="positive", impact_score=48, published_at=_ago(6),
                city_id=lahore.id, scheme_id=lsc.id,
                summary="New NOCs unlock construction activity and title transfers.",
                tags=["lda", "noc", "approval"],
            ),
            NewsItem(
                title="Lahore Ring Road Southern Loop opens, cutting travel time to Bahria and Smart City",
                source="The Express Tribune", channel_type="news", category="infrastructure",
                sentiment="positive", impact_score=52, published_at=_ago(13),
                city_id=lahore.id,
                summary="Connectivity improvement is historically associated with 8-15% price uplift nearby.",
                tags=["ring-road", "connectivity"],
            ),
            NewsItem(
                title="Pakistan property prices rise 6.4% YoY in urban centres — index report",
                source="Zameen Research", channel_type="research", category="market",
                sentiment="positive", impact_score=45, published_at=_ago(2),
                summary="Genuine end-user demand plus overseas remittances drive gains.",
                tags=["prices", "index"],
            ),
            NewsItem(
                title="Overseas remittances hit record high, boosting Gulf-based property investment",
                source="Dawn", channel_type="news", category="finance",
                sentiment="positive", impact_score=50, published_at=_ago(16),
                summary="Remittances are a key demand channel for DHA and Bahria products.",
                tags=["remittances", "overseas"],
            ),
            NewsItem(
                title="CDA announces new residential sectors in Islamabad; 8,000 plots to be balloted",
                source="CDA", channel_type="government", category="development",
                sentiment="positive", impact_score=42, published_at=_ago(21),
                city_id=islamabad.id,
                summary="Fresh supply in the capital; expect competition with private societies.",
                tags=["cda", "supply"],
            ),
            NewsItem(
                title="Karachi municipal authority seals illegal constructions in DHA-adjacent zones",
                source="Geo News", channel_type="news", category="regulation",
                sentiment="negative", impact_score=-35, published_at=_ago(8),
                city_id=karachi.id,
                summary="Enforcement raises short-term friction for buyers and developers.",
                tags=["enforcement", "illegal"],
            ),
            NewsItem(
                title="Political uncertainty ahead of by-elections slows large-ticket property decisions",
                source="Pakistan Today", channel_type="news", category="political",
                sentiment="negative", impact_score=-30, published_at=_ago(11),
                summary="Buyers typically pause big commitments around political events.",
                tags=["politics", "elections"],
            ),
            NewsItem(
                title="Islamabad Smart City launches third phase; 1,200 units released on instalments",
                source="Future Holdings", channel_type="developer", category="development",
                sentiment="positive", impact_score=44, published_at=_ago(5),
                city_id=islamabad.id, scheme_id=isb_sc.id,
                summary="Phased releases with payment plans target mid-income end users.",
                tags=["phase", "instalments"],
            ),
            NewsItem(
                title="Banks expand low-cost housing finance under SBP Mark-up Subsidy Scheme",
                source="SBP", channel_type="bank", category="finance",
                sentiment="positive", impact_score=38, published_at=_ago(19),
                summary="Subsidised mortgage tiers widen the affordable buyer pool.",
                tags=["mortgage", "subsidy"],
            ),
            NewsItem(
                title="Bahria Town Karachi utility dispute re-enters court; buyers seek escrow protection",
                source="Business Recorder", channel_type="news", category="regulation",
                sentiment="negative", impact_score=-42, published_at=_ago(3),
                city_id=karachi.id, scheme_id=bahria_khi.id,
                summary="Litigation risk weighs on resale liquidity in affected precincts.",
                tags=["litigation", "utilities"],
            ),
            NewsItem(
                title="Pakistan launches first REIT for commercial real estate, targeting institutional capital",
                source="Ministry of Housing", channel_type="government", category="finance",
                sentiment="positive", impact_score=40, published_at=_ago(24),
                summary="REITs could introduce long-term institutional demand for commercial stock.",
                tags=["reit", "institutional"],
            ),
            NewsItem(
                title="Urban population crosses 42% as rural-to-city migration accelerates",
                source="Pakistan Bureau of Statistics", channel_type="government", category="social",
                sentiment="positive", impact_score=36, published_at=_ago(27),
                summary="Structural housing demand driver across all major cities.",
                tags=["urbanisation", "population"],
            ),
            NewsItem(
                title="DHA Lahore Phase 9 commercial auctions fetch record per-marla bids",
                source="DHA", channel_type="developer", category="market",
                sentiment="positive", impact_score=47, published_at=_ago(7),
                city_id=lahore.id, scheme_id=dha_lhr.id,
                summary="Commercial auction strength signals confidence in mature societies.",
                tags=["auction", "commercial"],
            ),
            NewsItem(
                title="Construction material prices ease 5% as cement and steel stabilise",
                source="Graana Research", channel_type="research", category="development",
                sentiment="positive", impact_score=33, published_at=_ago(14),
                summary="Lower input costs improve developer margins and completion rates.",
                tags=["construction", "cost"],
            ),
            NewsItem(
                title="Provincial government proposes higher property tax on vacant plots",
                source="Dawn", channel_type="news", category="policy",
                sentiment="negative", impact_score=-28, published_at=_ago(10),
                summary="Vacant-plot levies discourage speculative holding and raise carry cost.",
                tags=["property-tax", "speculation"],
            ),
            NewsItem(
                title="Karachi BRT and Red Line progress boosts adjoining residential demand",
                source="The Express Tribune", channel_type="news", category="infrastructure",
                sentiment="positive", impact_score=34, published_at=_ago(18),
                city_id=karachi.id,
                summary="Transit corridors lift rental and capital values along the route.",
                tags=["brt", "transit"],
            ),
        ]
    )

    # ---- Authentication: demo accounts ----
    auth.seed_users()

    # ---- Accounting: chart of accounts + ~14 months of transactions ----
    _seed_accounting()

    # ---- Spatial: points of interest + saved areas of interest ----
    _seed_pois()
    _seed_aois()

    # ---- Portal content: pages, history, contacts, stories, advertisements ----
    _seed_content()

    # ---- Construction & maintenance wings ----
    _seed_construction()
    _seed_maintenance()

    # ---- Agentic OS, transactions, leasing, marketing, commercialization ----
    _seed_agentic_os()

    # ---- Tools & Utilities wing ----
    _seed_tools()

    # ---- PMO wing (project management, monitoring & tracking) ----
    _seed_pmo()

    # ---- Team messaging & notifications wing ----
    _seed_messaging()

    # ---- DHA master plans (if built): schemes + GIS layers ----
    _seed_master_plans()


init_sample_data()


# ============================================================
# ENTRY POINT
# ============================================================


def main() -> None:
    print("Real Estate Portal MCP Server")
    print("=" * 60)
    print("Hierarchy : City -> Scheme -> Block/Area -> Property")
    print("GIS       : coordinates, Haversine, nearby search")
    print("Memory    : near cache + long-term memory")
    print("RAG       : natural-language retrieval + insights")
    print("Projects  : mall / tower / mixed-use / compound / plaza")
    print("Images    : galleries for every entity")
    print("CRM       : agents, leads, customers, deals, tasks")
    print("Accounting: double-entry ledger, invoices, rent roll, ROI/IRR")
    print("Spatial   : POI (points of interest) + AOI (areas of interest)")
    print("Routing   : on foot / bicycle / motor car — best & alternative routes")
    print("Portal    : content pages, history, success stories, ads, users & roles")
    print("Construction: techniques, cost estimation, impact, codes & approvals")
    print("Maintenance: services, lifecycle, condition, repair vs replace, cost")
    print("Agentic OS: 24 agents, smart actions, audited runs, MCP dispatch")
    print("Deals     : transactions, offers, deadlines, e-signatures, commission→ledger")
    print("Intelligence: buyer agent, seller CMA, investment screener")
    print("Leasing   : 24/7 inquiry handling, screening, renewals, rent floor")
    print("Marketing : lead engine, routing, re-engagement, content, campaigns")
    print("Commercial: 8 products, hybrid pricing, metering, billing, payouts")
    print("Tools     : calculators, GIS/georeferencing, CAD, photo, documents, calendar")
    print("PMO       : project register, CPM scheduling, EVM, cost & risk control, site diary")
    print("Messaging : internal chat, channels, property threads, notifications, Telegram alerts")
    print(f"Data      : {len(properties_db)} properties, {len(big_projects_db)} big projects, {len(leads_db)} leads")
    print(f"Content   : {len(content.pages_db)} pages, {len(content.stories_db)} stories, {len(content.ads_db)} ads, {len(auth.users_db)} users")
    print(f"Wings     : {len(construction.estimates_db)} build estimates, {len(maintenance.plans_db)} maintenance plans, {len(maintenance.work_orders_db)} work orders")
    print(f"Agentic   : {len(agents.AGENTS)} agents, {len(agents.runs_db)} runs, {len(transactions.transactions_db)} transactions, {len(commercial.PRODUCTS)} products")
    print(f"Toolbox   : {len(tools.TOOL_CATALOG)} tools in {len(tools.TOOL_CATEGORIES)} categories, {len(tools.projects_db)} saved projects")
    print(f"PMO       : {len(pmo.projects_db)} projects, {len(pmo.tasks_db)} tasks, {len(pmo.risks_db)} risks, {len(pmo.cost_entries_db)} cost entries")
    print(f"Messaging : {len(messaging.conversations_db)} conversations, {len(messaging.messages_db)} messages, {len(messaging.notifications_db)} notifications, {len(messaging.outbox_db)} outbox items")
    print("=" * 60)
    mcp.run()


if __name__ == "__main__":
    main()
