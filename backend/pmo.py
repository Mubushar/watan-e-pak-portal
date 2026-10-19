"""
Project Management & Monitoring (PMO) wing for the Real Estate Portal
=====================================================================

An in-house, running **project management, monitoring and tracking** system for
the projects the portal itself delivers — residential and commercial builds,
land development and infrastructure.  It is the operational layer that sits on
top of the *construction* wing (which estimates) and the *maintenance* wing
(which looks after the asset after handover):

* **Portfolio & project register** — projects with type, sponsor, city, scheme,
  manager, baseline budget/dates, contract value, status and priority.
* **WBS, phases & milestones** — a work-breakdown with weighted phases, payment
  milestones and tasks carrying durations, predecessors and assignees.
* **Scheduling** — a forward/backward pass over the task network (finish-to-start
  dependencies, a six-day Pakistani working week), giving earliest/latest start
  and finish, total float, the **critical path** and a Gantt structure.
* **Progress & earned value** — duration-weighted completion, a planned-vs-actual
  **S-curve**, and full EVM (PV, EV, AC, SV, CV, SPI, CPI, EAC, ETC, VAC, TCPI).
* **Cost control** — baseline, approved variations, revised budget, commitments,
  actual cost by category, forecast-to-complete and variance.
* **Monitoring & tracking** — schedule/cost/risk/quality **RAG health**, an
  exception-based alert engine, KPI scorecards and a portfolio dashboard.
* **Resources** — team & trade resources, task allocations and a loading /
  over-allocation view over any window.
* **RAID, site diary, change control, quality and actions** — risk register with
  a probability × impact matrix, daily site logs, variation requests with cost &
  schedule impact, inspection checklists and meeting action items.
* **Reports** — a full project status report as JSON and as printable HTML.

No MCP or FastAPI code lives here: ``server.py`` exposes these functions over MCP
and ``api.py`` reuses the very same functions over REST.  ``gis`` renders the
plain dicts this module returns into themed, bilingual pages.
"""

import math
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

import gis

# ============================================================
# CONFIGURATION
# ============================================================

PMO_CONFIG: Dict[str, Any] = {
    "currency": "PKR",
    "currency_symbol": "Rs",
    "working_days_per_week": 6,          # Mon–Sat (Sunday off)
    "rest_weekday": 6,                   # Python weekday(): 0=Mon … 6=Sun
    "default_shift_hours": 8,
    "default_project_type": "construction",
    "default_priority": "medium",
    "net_working_days_per_month": 26.0,
    # Earned-value / health thresholds
    "spi_green": 0.95, "spi_amber": 0.90,
    "cpi_green": 0.95, "cpi_amber": 0.90,
    "slip_amber_days": 5, "slip_red_days": 15,
    "cost_overrun_amber_pct": 3.0, "cost_overrun_red_pct": 8.0,
    "quality_green": 85.0, "quality_amber": 70.0,
    "risk_amber_score": 10, "risk_red_score": 16,
    "stale_progress_days": 14,           # no update for this long -> alert
    "overalloc_threshold_pct": 100.0,
    "default_contingency_pct": 5.0,
    "eac_method": "cpi",                 # 'cpi' | 'budget' | 'composite'
    "disclaimer": (
        "Planned/earned-value figures are indicative management information. "
        "Date arithmetic uses a six-day (Mon–Sat) working week; align with the "
        "contract's own calendar before use in formal claims."
    ),
}

PROJECT_TYPES: Dict[str, Dict[str, Any]] = {
    "construction": {"label": "Building construction", "icon": "building"},
    "development": {"label": "Housing scheme / development", "icon": "map"},
    "infrastructure": {"label": "Infrastructure & utilities", "icon": "road"},
    "land_development": {"label": "Land development & plotting", "icon": "grid"},
    "renovation": {"label": "Renovation & retrofit", "icon": "wrench"},
    "fitout": {"label": "Interior fit-out", "icon": "sofa"},
    "master_planning": {"label": "Master planning & feasibility", "icon": "compass"},
    "maintenance": {"label": "Facility / maintenance project", "icon": "shield"},
}

PRIORITIES = ["low", "medium", "high", "critical"]
PROJECT_STATUSES = ["planning", "active", "on_hold", "completed", "cancelled"]
TASK_STATUSES = ["not_started", "in_progress", "blocked", "done"]
MILESTONE_STATUSES = ["pending", "at_risk", "met", "missed"]
RAID_KINDS = ["risk", "issue", "assumption", "dependency"]
RAID_STATUSES = ["open", "mitigating", "closed"]
CHANGE_STATUSES = ["draft", "submitted", "approved", "rejected"]
COST_KINDS = ["committed", "actual"]

COST_CATEGORIES: List[str] = [
    "land", "design", "approvals", "site_setup", "substructure", "structure",
    "masonry", "mep", "finishes", "external_works", "consultancy", "marketing",
    "finance", "contingency", "overhead", "other",
]

RISK_CATEGORIES: List[str] = [
    "design", "approvals", "procurement", "cost", "schedule", "quality",
    "safety", "weather", "finance", "legal", "community", "resources",
]

RISK_BANDS: Dict[str, Tuple[int, int]] = {
    "low": (1, 4), "medium": (5, 9), "high": (10, 15), "extreme": (16, 25),
}

RAG_COLORS: Dict[str, str] = {"green": "#1b9e4b", "amber": "#e6a100", "red": "#d81f2a"}

QUALITY_AREAS: List[str] = [
    "setting_out", "earthworks", "foundation", "structural_frame", "masonry",
    "plaster", "waterproofing", "electrical", "plumbing", "hvac", "finishes",
    "external_works",
]

# phase -> (key, label, weight %)
PHASE_TEMPLATES: Dict[str, List[Tuple[str, str, float]]] = {
    "construction": [
        ("design", "Design & Approvals", 8.0),
        ("procurement", "Procurement & Mobilisation", 4.0),
        ("substructure", "Substructure / Foundation", 14.0),
        ("superstructure", "Superstructure / Frame", 28.0),
        ("masonry", "Masonry & Plaster", 12.0),
        ("mep", "MEP Rough-in", 12.0),
        ("finishes", "Finishes & Fittings", 12.0),
        ("external", "External Works & Landscaping", 5.0),
        ("handover", "Testing, Snagging & Handover", 5.0),
    ],
    "development": [
        ("feasibility", "Feasibility & Master Plan", 8.0),
        ("approvals", "Approvals & NOC", 10.0),
        ("land", "Land Acquisition & Possession", 12.0),
        ("infrastructure", "Roads, Water & Utilities", 22.0),
        ("plots", "Plot Development & Marking", 16.0),
        ("amenities", "Amenities & Landscape", 14.0),
        ("marketing", "Marketing & Sales", 10.0),
        ("handover", "Handover & Society Formation", 8.0),
    ],
    "infrastructure": [
        ("survey", "Survey & Design", 12.0),
        ("approvals", "Approvals & Way-leaves", 8.0),
        ("earthworks", "Earthworks", 20.0),
        ("structures", "Structures", 25.0),
        ("utilities", "Utilities & Services", 20.0),
        ("commissioning", "Testing & Commissioning", 8.0),
        ("handover", "Handover", 7.0),
    ],
    "renovation": [
        ("survey", "Survey & Condition Report", 10.0),
        ("design", "Design & Approvals", 10.0),
        ("strip", "Strip-out & Demolition", 15.0),
        ("structure", "Structural Repairs", 20.0),
        ("services", "Services Replacement", 20.0),
        ("finishes", "Finishes & Fittings", 20.0),
        ("handover", "Snagging & Handover", 5.0),
    ],
    "fitout": [
        ("design", "Design & Shop Drawings", 15.0),
        ("procurement", "Procurement", 15.0),
        ("services", "MEP & Ceiling", 25.0),
        ("joinery", "Joinery & Furniture", 25.0),
        ("finishes", "Finishes & Décor", 15.0),
        ("handover", "Snagging & Handover", 5.0),
    ],
    "master_planning": [
        ("data", "Data & Site Analysis", 20.0),
        ("concept", "Concept Master Plan", 25.0),
        ("financial", "Financial Feasibility", 20.0),
        ("approvals", "Regulatory Review", 20.0),
        ("report", "Report & Handover", 15.0),
    ],
    "land_development": [
        ("survey", "Survey & Layout", 15.0),
        ("levelling", "Levelling & Earthworks", 25.0),
        ("roads", "Roads & Drainage", 25.0),
        ("utilities", "Utilities & Services", 20.0),
        ("handover", "Demarcation & Handover", 15.0),
    ],
    "maintenance": [
        ("survey", "Condition Survey", 20.0),
        ("scope", "Scope & Costing", 15.0),
        ("works", "Repair & Replacement Works", 45.0),
        ("commissioning", "Testing", 10.0),
        ("handover", "Close-out & Handover", 10.0),
    ],
}

# WBS template for a building: (phase_key, task name, working days, cost % , predecessors by index)
WBS_CONSTRUCTION: List[Tuple[str, str, int, float, List[int]]] = [
    ("design", "Architectural drawings & approvals set", 20, 2.0, []),
    ("design", "Structural & MEP design", 15, 1.5, [0]),
    ("design", "LDA / authority approvals & NOC", 30, 1.0, [0]),
    ("procurement", "Tender, award & contracts", 15, 0.0, [1, 2]),
    ("procurement", "Mobilisation & site setup", 10, 1.5, [3]),
    ("substructure", "Excavation & PCC", 12, 3.0, [4]),
    ("substructure", "Foundation & raft", 20, 8.0, [5]),
    ("superstructure", "Ground-floor frame", 25, 12.0, [6]),
    ("superstructure", "Upper-floor frames", 30, 16.0, [7]),
    ("masonry", "Masonry & internal plaster", 30, 10.0, [8]),
    ("mep", "MEP rough-in (electrical, plumbing, HVAC)", 25, 10.0, [8]),
    ("finishes", "Flooring, tiling & ceilings", 25, 9.0, [9]),
    ("finishes", "Painting, joinery & fittings", 20, 6.0, [10, 11]),
    ("external", "External works & landscaping", 20, 5.0, [12]),
    ("handover", "Testing & commissioning", 12, 3.0, [13]),
    ("handover", "Snagging & handover", 10, 2.0, [14]),
]

# A lighter WBS reused for non-building project types (keys differ, so we map by phase)
WBS_GENERIC: Dict[str, List[Tuple[str, str, int, float, List[int]]]] = {
    "development": [
        ("feasibility", "Market & site feasibility", 25, 5.0, []),
        ("approvals", "Layout plan & NOC approvals", 40, 6.0, [0]),
        ("land", "Land acquisition & possession", 35, 20.0, [0]),
        ("infrastructure", "Roads, water supply & sewerage", 60, 30.0, [1, 2]),
        ("infrastructure", "Electricity & street lighting", 30, 10.0, [3]),
        ("plots", "Plot cutting & demarcation", 40, 12.0, [3]),
        ("amenities", "Park, mosque & amenities", 35, 9.0, [4]),
        ("marketing", "Sales launch & marketing", 30, 3.0, [2]),
        ("handover", "Society formation & handover", 25, 5.0, [6, 7]),
    ],
    "renovation": [
        ("survey", "Condition survey & report", 12, 3.0, []),
        ("design", "Design & approvals", 15, 5.0, [0]),
        ("strip", "Strip-out & demolition", 15, 8.0, [1]),
        ("structure", "Structural repairs & strengthening", 25, 22.0, [2]),
        ("services", "Electrical & plumbing replacement", 25, 20.0, [3]),
        ("finishes", "Finishes, paint & joinery", 30, 35.0, [4]),
        ("handover", "Snagging & handover", 8, 7.0, [5]),
    ],
}

PM_CAPABILITIES: List[Dict[str, Any]] = [
    {"key": "register", "name": "Project Register", "category": "portfolio",
     "blurb": "Projects with sponsor, manager, budget, dates, status and priority."},
    {"key": "wbs", "name": "WBS, Phases & Milestones", "category": "planning",
     "blurb": "Weighted phases, payment milestones and a task work-breakdown."},
    {"key": "schedule", "name": "Scheduling & Critical Path", "category": "planning",
     "blurb": "Forward/backward pass, float, critical path and a Gantt structure."},
    {"key": "progress", "name": "Progress Tracking", "category": "tracking",
     "blurb": "Duration-weighted completion and a planned-vs-actual S-curve."},
    {"key": "evm", "name": "Earned Value (EVM)", "category": "tracking",
     "blurb": "PV, EV, AC, SV, CV, SPI, CPI, EAC, ETC, VAC and TCPI."},
    {"key": "cost", "name": "Cost Control", "category": "tracking",
     "blurb": "Baseline, variations, commitments, actuals and forecast to complete."},
    {"key": "health", "name": "Health & Alerts", "category": "monitoring",
     "blurb": "Schedule/cost/risk/quality RAG status and exception alerts."},
    {"key": "resources", "name": "Resource Loading", "category": "monitoring",
     "blurb": "Team & trade allocations, utilisation and over-allocation flags."},
    {"key": "raid", "name": "Risk Register (RAID)", "category": "governance",
     "blurb": "Risks, issues, assumptions and dependencies with a P×I matrix."},
    {"key": "site", "name": "Site Diary", "category": "tracking",
     "blurb": "Daily site logs — weather, manpower, plant, work done and safety."},
    {"key": "change", "name": "Change Control", "category": "governance",
     "blurb": "Variation requests with cost and schedule impact and approval."},
    {"key": "quality", "name": "Quality & Inspections", "category": "governance",
     "blurb": "Stage inspection checklists scored into a quality index."},
    {"key": "actions", "name": "Meeting Actions", "category": "governance",
     "blurb": "Action items with owners, due dates and close-out."},
    {"key": "kpi", "name": "KPI Scorecard", "category": "monitoring",
     "blurb": "A scorecard of the KPIs that matter to each project."},
    {"key": "report", "name": "Status Reports", "category": "reporting",
     "blurb": "A full project status report as JSON and printable HTML."},
    {"key": "portfolio", "name": "Portfolio Dashboard", "category": "reporting",
     "blurb": "One view across every running project with rolled-up EVM."},
]

DISCLAIMER = PMO_CONFIG["disclaimer"]


# ============================================================
# HELPERS
# ============================================================


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _today() -> date:
    return date.today()


def _new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


def _m(model: BaseModel) -> Dict[str, Any]:
    return model.model_dump(mode="json")


def _round(value: Any, digits: int = 2) -> float:
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return 0.0


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def format_pkr(amount: float, symbol: str = "Rs") -> str:
    """Compact PKR string for reports."""
    a = _num(amount)
    if abs(a) >= 1_000_000_000:
        return f"{symbol} {a / 1_000_000_000:,.2f}B"
    if abs(a) >= 1_000_000:
        return f"{symbol} {a / 1_000_000:,.2f}M"
    if abs(a) >= 1_000:
        return f"{symbol} {a / 1_000:,.1f}K"
    return f"{symbol} {a:,.0f}"


def _as_date(value: Any, default: Optional[date] = None) -> date:
    if value is None or value == "":
        return default or _today()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip().replace("Z", "")
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d").date()
        except ValueError:
            return default or _today()


def _iso(value: Any, default: Optional[date] = None) -> Optional[str]:
    if value is None or value == "":
        if default is None:
            return None
        return default.isoformat()
    return _as_date(value, default).isoformat()


def _is_workday(d: date) -> bool:
    return d.weekday() != PMO_CONFIG["rest_weekday"]


def _next_workday(d: date) -> date:
    while not _is_workday(d):
        d = d + timedelta(days=1)
    return d


def add_working_days(start: Any, days: int) -> date:
    """Return the date ``days`` working days after ``start`` (start = day 0)."""
    d = _next_workday(_as_date(start))
    n = int(days)
    step = 1 if n >= 0 else -1
    remaining = abs(n)
    while remaining > 0:
        d = d + timedelta(days=step)
        if _is_workday(d):
            remaining -= 1
    return d


def working_days_between(a: Any, b: Any) -> int:
    """Number of working days in the half-open interval ``(a, b]``."""
    start, end = _as_date(a), _as_date(b)
    if end <= start:
        return 0
    n = 0
    d = start
    while d < end:
        d = d + timedelta(days=1)
        if _is_workday(d):
            n += 1
    return n


def risk_band(score: float) -> str:
    s = int(_num(score))
    for band, (lo, hi) in RISK_BANDS.items():
        if lo <= s <= hi:
            return band
    return "extreme" if s > 25 else "low"


def _rag(value: float, green: float, amber: float) -> str:
    """Higher-is-better RAG (value >= green -> green)."""
    if value >= green:
        return "green"
    if value >= amber:
        return "amber"
    return "red"


def _worst(*bands: str) -> str:
    order = {"green": 0, "amber": 1, "red": 2}
    worst = "green"
    for b in bands:
        if order.get(b, 0) > order.get(worst, 0):
            worst = b
    return worst


# ============================================================
# MODELS
# ============================================================


class PMProject(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("pm_"))
    code: str = ""
    name: str
    project_type: str = "construction"
    description: Optional[str] = None
    city: Optional[str] = None
    scheme: Optional[str] = None
    client: Optional[str] = None
    manager_id: Optional[str] = None
    status: str = "planning"
    priority: str = "medium"
    start_date: str = Field(default_factory=lambda: _today().isoformat())
    end_date: Optional[str] = None
    baseline_start: Optional[str] = None
    baseline_end: Optional[str] = None
    baseline_budget: float = 0.0
    budget: float = 0.0
    contract_value: float = 0.0
    currency: str = "PKR"
    tags: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)


class PmPhase(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("pmph_"))
    project_id: str
    key: str
    name: str
    order: int = 0
    weight: float = 0.0
    status: str = "not_started"
    planned_start: Optional[str] = None
    planned_end: Optional[str] = None
    actual_start: Optional[str] = None
    actual_end: Optional[str] = None
    notes: Optional[str] = None


class PmMilestone(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("pmm_"))
    project_id: str
    name: str
    phase_key: Optional[str] = None
    task_id: Optional[str] = None
    planned_date: Optional[str] = None
    forecast_date: Optional[str] = None
    actual_date: Optional[str] = None
    weight: float = 1.0
    status: str = "pending"
    billable_amount: float = 0.0
    invoice_ref: Optional[str] = None
    notes: Optional[str] = None


class PmTask(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("pmt_"))
    project_id: str
    phase_key: Optional[str] = None
    wbs: Optional[str] = None
    name: str
    assignee_id: Optional[str] = None
    duration_days: int = 1
    predecessors: List[str] = Field(default_factory=list)
    progress_pct: float = 0.0
    status: str = "not_started"
    priority: str = "medium"
    weight: float = 0.0
    cost_budget: float = 0.0
    actual_start: Optional[str] = None
    actual_finish: Optional[str] = None
    notes: Optional[str] = None
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)


class PmResource(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("pmr_"))
    name: str
    role: str = "engineer"
    trade: Optional[str] = None
    day_rate: float = 0.0
    capacity_pct: float = 100.0
    skills: List[str] = Field(default_factory=list)
    contact: Optional[str] = None
    active: bool = True


class PmAllocation(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("pma_"))
    project_id: str
    task_id: str
    resource_id: str
    units_pct: float = 100.0
    notes: Optional[str] = None


class PmCostEntry(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("pmc_"))
    project_id: str
    date: str = Field(default_factory=lambda: _today().isoformat())
    category: str = "other"
    description: str = ""
    amount: float = 0.0
    kind: str = "actual"
    vendor: Optional[str] = None
    invoice_ref: Optional[str] = None
    recorded_by: Optional[str] = None


class PmProgressUpdate(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("pmu_"))
    project_id: str
    date: str = Field(default_factory=lambda: _today().isoformat())
    percent: float = 0.0
    note: Optional[str] = None
    by: Optional[str] = None
    manpower: int = 0
    weather: Optional[str] = None


class PmRisk(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("pmrk_"))
    project_id: str
    kind: str = "risk"
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    probability: int = 3
    impact: int = 3
    owner: Optional[str] = None
    mitigation: Optional[str] = None
    status: str = "open"
    raised_on: str = Field(default_factory=lambda: _today().isoformat())
    due_on: Optional[str] = None


class PmSiteLog(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("pmsl_"))
    project_id: str
    date: str = Field(default_factory=lambda: _today().isoformat())
    weather: Optional[str] = None
    manpower: int = 0
    equipment: List[str] = Field(default_factory=list)
    work_done: Optional[str] = None
    issues: Optional[str] = None
    safety_incidents: int = 0
    visitors: Optional[str] = None
    photos: List[str] = Field(default_factory=list)
    by: Optional[str] = None


class PmChangeRequest(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("pmcr_"))
    project_id: str
    title: str
    description: Optional[str] = None
    reason: Optional[str] = None
    cost_impact: float = 0.0
    schedule_impact_days: int = 0
    status: str = "draft"
    requested_by: Optional[str] = None
    decided_by: Optional[str] = None
    decided_on: Optional[str] = None
    decision_note: Optional[str] = None
    raised_on: str = Field(default_factory=lambda: _today().isoformat())


class PmChecklistItem(BaseModel):
    item: str
    result: str = "pending"        # pass | fail | na | pending
    note: Optional[str] = None


class PmInspection(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("pmi_"))
    project_id: str
    title: str
    phase_key: Optional[str] = None
    area: Optional[str] = None
    inspector: Optional[str] = None
    date: str = Field(default_factory=lambda: _today().isoformat())
    checklist: List[PmChecklistItem] = Field(default_factory=list)
    status: str = "open"
    notes: Optional[str] = None


class PmAction(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("pmact_"))
    project_id: str
    title: str
    meeting: Optional[str] = None
    owner: Optional[str] = None
    due_on: Optional[str] = None
    priority: str = "medium"
    status: str = "open"
    notes: Optional[str] = None
    created_at: str = Field(default_factory=_now)


# ---- stores ----
projects_db: List[PMProject] = []
phases_db: List[PmPhase] = []
milestones_db: List[PmMilestone] = []
tasks_db: List[PmTask] = []
resources_db: List[PmResource] = []
allocations_db: List[PmAllocation] = []
cost_entries_db: List[PmCostEntry] = []
progress_updates_db: List[PmProgressUpdate] = []
risks_db: List[PmRisk] = []
site_logs_db: List[PmSiteLog] = []
change_requests_db: List[PmChangeRequest] = []
inspections_db: List[PmInspection] = []
actions_db: List[PmAction] = []


# ---- lookups ----
def find_project(project_id: Optional[str]) -> Optional[PMProject]:
    if not project_id:
        return None
    key = str(project_id).strip()
    for p in projects_db:
        if p.id == key or p.code.upper() == key.upper():
            return p
    return None


def find_resource(resource_id: Optional[str]) -> Optional[PmResource]:
    return next((r for r in resources_db if r.id == resource_id), None)


def find_task(task_id: Optional[str]) -> Optional[PmTask]:
    return next((t for t in tasks_db if t.id == task_id), None)


def find_risk(risk_id: Optional[str]) -> Optional[PmRisk]:
    return next((r for r in risks_db if r.id == risk_id), None)


def find_change(change_id: Optional[str]) -> Optional[PmChangeRequest]:
    return next((c for c in change_requests_db if c.id == change_id), None)


def find_action(action_id: Optional[str]) -> Optional[PmAction]:
    return next((a for a in actions_db if a.id == action_id), None)


def tasks_for(project_id: str) -> List[PmTask]:
    return [t for t in tasks_db if t.project_id == project_id]


def phases_for(project_id: str) -> List[PmPhase]:
    return sorted([p for p in phases_db if p.project_id == project_id], key=lambda p: (p.order, p.name))


def milestones_for(project_id: str) -> List[PmMilestone]:
    return [m for m in milestones_db if m.project_id == project_id]


def costs_for(project_id: str) -> List[PmCostEntry]:
    return [c for c in cost_entries_db if c.project_id == project_id]


def risks_for(project_id: str) -> List[PmRisk]:
    return [r for r in risks_db if r.project_id == project_id]


def changes_for(project_id: str) -> List[PmChangeRequest]:
    return [c for c in change_requests_db if c.project_id == project_id]


def _next_code() -> str:
    return f"PRJ-{len(projects_db) + 1:04d}"


# ============================================================
# PROJECT REGISTER
# ============================================================


def project_types() -> Dict[str, Any]:
    """The supported project types."""
    return {"count": len(PROJECT_TYPES), "types": PROJECT_TYPES,
            "statuses": PROJECT_STATUSES, "priorities": PRIORITIES}


def phase_templates(project_type: Optional[str] = None) -> Dict[str, Any]:
    """Default weighted phase templates by project type."""
    if project_type:
        rows = PHASE_TEMPLATES.get(project_type)
        if rows is None:
            return {"error": f"Unknown project type: {project_type}",
                    "types": sorted(PHASE_TEMPLATES)}
        return {"project_type": project_type,
                "phases": [{"key": k, "name": n, "weight": w} for k, n, w in rows]}
    return {"templates": {t: [{"key": k, "name": n, "weight": w} for k, n, w in rows]
                          for t, rows in PHASE_TEMPLATES.items()}}


def create_project(
    name: str,
    project_type: str = "construction",
    description: Optional[str] = None,
    city: Optional[str] = None,
    scheme: Optional[str] = None,
    client: Optional[str] = None,
    manager_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    budget: float = 0.0,
    contract_value: float = 0.0,
    priority: str = "medium",
    status: str = "planning",
    tags: Optional[List[str]] = None,
    with_template: bool = True,
) -> Dict[str, Any]:
    """Create a project, optionally seeding its phase template and WBS."""
    ptype = project_type if project_type in PROJECT_TYPES else "construction"
    project = PMProject(
        code=_next_code(), name=name, project_type=ptype, description=description,
        city=city, scheme=scheme, client=client, manager_id=manager_id,
        status=status if status in PROJECT_STATUSES else "planning",
        priority=priority if priority in PRIORITIES else "medium",
        start_date=_iso(start_date, _today()),
        end_date=_iso(end_date),
        baseline_start=_iso(start_date, _today()),
        baseline_budget=_num(budget), budget=_num(budget),
        contract_value=_num(contract_value), tags=list(tags or []),
    )
    projects_db.append(project)
    if with_template:
        apply_template(project.id, ptype)
    project.updated_at = _now()
    return {"project": _m(project), "created": True,
            "phases": len(phases_for(project.id)), "tasks": len(tasks_for(project.id))}


def list_projects(
    status: Optional[str] = None,
    project_type: Optional[str] = None,
    city: Optional[str] = None,
    manager_id: Optional[str] = None,
    priority: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    rows = list(projects_db)
    if status:
        rows = [p for p in rows if p.status == status]
    if project_type:
        rows = [p for p in rows if p.project_type == project_type]
    if city:
        rows = [p for p in rows if (p.city or "").lower() == city.lower()]
    if manager_id:
        rows = [p for p in rows if p.manager_id == manager_id]
    if priority:
        rows = [p for p in rows if p.priority == priority]
    rows = sorted(rows, key=lambda p: p.created_at, reverse=True)
    return {"count": len(rows), "projects": [
        {"id": p.id, "code": p.code, "name": p.name, "project_type": p.project_type,
         "city": p.city, "status": p.status, "priority": p.priority,
         "start_date": p.start_date, "end_date": p.end_date,
         "budget": p.budget, "progress_pct": project_progress(p.id)["actual_pct"],
         "health": project_health(p.id)["overall"]}
        for p in rows[:limit]
    ]}


def get_project(project_id: str) -> Dict[str, Any]:
    p = find_project(project_id)
    if not p:
        return {"error": f"Unknown project: {project_id}",
                "projects": [{"id": x.id, "code": x.code, "name": x.name} for x in projects_db]}
    return {"project": _m(p), "phase_count": len(phases_for(p.id)),
            "task_count": len(tasks_for(p.id)),
            "milestone_count": len(milestones_for(p.id))}


def update_project(project_id: str, **fields: Any) -> Dict[str, Any]:
    p = find_project(project_id)
    if not p:
        return {"error": f"Unknown project: {project_id}"}
    allowed = {"name", "project_type", "description", "city", "scheme", "client",
               "manager_id", "status", "priority", "start_date", "end_date",
               "baseline_start", "baseline_end", "baseline_budget", "budget",
               "contract_value", "tags", "notes"}
    applied: Dict[str, Any] = {}
    for key, value in fields.items():
        if key not in allowed or value is None:
            continue
        if key in ("start_date", "end_date", "baseline_start", "baseline_end"):
            value = _iso(value)
        if key in ("baseline_budget", "budget", "contract_value"):
            value = _num(value)
        setattr(p, key, value)
        applied[key] = value
    p.updated_at = _now()
    return {"updated": applied, "project": _m(p)}


def delete_project(project_id: str) -> Dict[str, Any]:
    p = find_project(project_id)
    if not p:
        return {"error": f"Unknown project: {project_id}"}
    pid = p.id
    projects_db.remove(p)
    for store in (phases_db, milestones_db, tasks_db, cost_entries_db, progress_updates_db,
                  risks_db, site_logs_db, change_requests_db, inspections_db, actions_db):
        store[:] = [row for row in store if getattr(row, "project_id", None) != pid]
    allocations_db[:] = [a for a in allocations_db if find_task(a.task_id)]
    return {"deleted": True, "id": pid}


def apply_template(project_id: str, project_type: Optional[str] = None) -> Dict[str, Any]:
    """Seed the weighted phases and a task work-breakdown for a project."""
    p = find_project(project_id)
    if not p:
        return {"error": f"Unknown project: {project_id}"}
    ptype = project_type or p.project_type or "construction"
    phase_rows = PHASE_TEMPLATES.get(ptype, PHASE_TEMPLATES["construction"])
    created_phases: List[PmPhase] = []
    for order, (key, label, weight) in enumerate(phase_rows):
        if any(ph.project_id == p.id and ph.key == key for ph in phases_db):
            continue
        ph = PmPhase(project_id=p.id, key=key, name=label, order=order, weight=weight)
        phases_db.append(ph)
        created_phases.append(ph)

    wbs = WBS_GENERIC.get(ptype, WBS_CONSTRUCTION)
    by_index: Dict[int, PmTask] = {}
    created_tasks: List[PmTask] = []
    existing = {(t.phase_key, t.name): t for t in tasks_for(p.id)}
    for idx, (phase_key, name, days, cost_pct, deps) in enumerate(wbs):
        task = existing.get((phase_key, name))
        if task is None:
            task = PmTask(
                project_id=p.id, phase_key=phase_key, wbs=f"{idx + 1:02d}", name=name,
                duration_days=int(days), cost_budget=_round(p.budget * cost_pct / 100.0),
                predecessors=[by_index[d].id for d in deps if d in by_index],
            )
            tasks_db.append(task)
            created_tasks.append(task)
        elif not task.predecessors:
            task.predecessors = [by_index[d].id for d in deps if d in by_index]
        by_index[idx] = task

    if not milestones_for(p.id) and p.budget > 0:
        _seed_milestones_from_wbs(p)
    p.updated_at = _now()
    return {"project_id": p.id, "project_type": ptype,
            "phases_created": len(created_phases), "tasks_created": len(created_tasks),
            "total_phases": len(phases_for(p.id)), "total_tasks": len(tasks_for(p.id))}


def _seed_milestones_from_wbs(project: PMProject) -> None:
    tasks = tasks_for(project.id)
    if not tasks:
        return
    picks = [(tasks[-1].id, "Practical completion", 60.0)]
    if len(tasks) >= 2:
        picks.insert(0, (tasks[0].id, "Design & approvals complete", 15.0))
    if len(tasks) >= 8:
        picks.insert(1, (tasks[7].id, "Structure complete", 25.0))
    for task_id, name, pct in picks:
        task = find_task(task_id)
        milestones_db.append(PmMilestone(
            project_id=project.id, name=name, task_id=task_id,
            phase_key=task.phase_key if task else None,
            planned_date=task.actual_finish or None,
            billable_amount=_round(project.contract_value * pct / 100.0),
        ))


def import_construction_estimate(
    estimate_id: str, name: Optional[str] = None, city: Optional[str] = None,
    start_date: Optional[str] = None, contract_value: Optional[float] = None,
) -> Dict[str, Any]:
    """Create a PMO project from a Construction-wing saved estimate (budget = build cost)."""
    import construction

    est = construction.find_estimate(estimate_id)
    if not est:
        return {"error": f"Unknown estimate: {estimate_id}",
                "estimates": [{"id": e.id, "title": e.title} for e in construction.estimates_db]}
    budget = _num(est.total_cost)
    res = create_project(
        name=name or f"{est.title} — delivery",
        project_type="construction", description=f"Delivery of estimate {est.id} ({est.title})",
        city=city or est.city, client=None, start_date=start_date,
        budget=budget, contract_value=_num(contract_value if contract_value is not None else budget * 1.15),
        status="active", with_template=True,
    )
    project = res["project"]
    update_project(project["id"], baseline_budget=budget, budget=budget,
                   notes=f"Imported from construction estimate {est.id}")
    return {"created": True, "project": get_project(project["id"])["project"],
            "source_estimate": {"id": est.id, "title": est.title, "total_cost": budget,
                                "duration_days": est.duration_days}}


# ============================================================
# WBS: PHASES, MILESTONES, TASKS
# ============================================================


def add_phase(project_id: str, name: str, key: Optional[str] = None, weight: float = 0.0,
              order: Optional[int] = None, planned_start: Optional[str] = None,
              planned_end: Optional[str] = None) -> Dict[str, Any]:
    p = find_project(project_id)
    if not p:
        return {"error": f"Unknown project: {project_id}"}
    ph = PmPhase(
        project_id=p.id, key=key or (name.lower().replace(" ", "_")[:24]),
        name=name, weight=_num(weight),
        order=int(order) if order is not None else len(phases_for(p.id)),
        planned_start=_iso(planned_start), planned_end=_iso(planned_end),
    )
    phases_db.append(ph)
    return {"created": True, "phase": _m(ph), "count": len(phases_for(p.id))}


def list_phases(project_id: str) -> Dict[str, Any]:
    p = find_project(project_id)
    if not p:
        return {"error": f"Unknown project: {project_id}"}
    rows = phases_for(p.id)
    total_weight = sum(ph.weight for ph in rows) or 1.0
    return {"count": len(rows), "phases": [
        {**_m(ph), "weight_pct": _round(ph.weight / total_weight * 100.0, 2),
         "progress_pct": _phase_progress(ph)}
        for ph in rows]}


def add_milestone(project_id: str, name: str, planned_date: Optional[str] = None,
                  phase_key: Optional[str] = None, task_id: Optional[str] = None,
                  weight: float = 1.0, billable_amount: float = 0.0,
                  notes: Optional[str] = None) -> Dict[str, Any]:
    p = find_project(project_id)
    if not p:
        return {"error": f"Unknown project: {project_id}"}
    m = PmMilestone(
        project_id=p.id, name=name, phase_key=phase_key, task_id=task_id,
        planned_date=_iso(planned_date), weight=_num(weight, 1.0),
        billable_amount=_num(billable_amount), notes=notes,
    )
    milestones_db.append(m)
    return {"created": True, "milestone": _m(m), "count": len(milestones_for(p.id))}


def list_milestones(project_id: str, status: Optional[str] = None) -> Dict[str, Any]:
    p = find_project(project_id)
    if not p:
        return {"error": f"Unknown project: {project_id}"}
    rows = milestones_for(p.id)
    if status:
        rows = [m for m in rows if m.status == status]
    return {"count": len(rows), "milestones": [_milestone_view(m) for m in rows]}


def _milestone_view(m: PmMilestone) -> Dict[str, Any]:
    forecast = m.forecast_date
    slip = 0
    if m.task_id:
        task = find_task(m.task_id)
        if task and not task.actual_finish:
            # forecast from the current schedule later; fall back to planned
            forecast = forecast or m.planned_date
    if forecast and m.planned_date:
        slip = working_days_between(m.planned_date, forecast)
    return {**_m(m), "forecast_date": forecast, "slip_days": slip}


def add_task(project_id: str, name: str, phase_key: Optional[str] = None,
             duration_days: int = 1, predecessors: Optional[List[str]] = None,
             assignee_id: Optional[str] = None, weight: float = 0.0,
             cost_budget: float = 0.0, priority: str = "medium",
             wbs: Optional[str] = None, notes: Optional[str] = None) -> Dict[str, Any]:
    p = find_project(project_id)
    if not p:
        return {"error": f"Unknown project: {project_id}"}
    task = PmTask(
        project_id=p.id, phase_key=phase_key, name=name, wbs=wbs,
        duration_days=max(1, int(duration_days)), predecessors=list(predecessors or []),
        assignee_id=assignee_id, weight=_num(weight), cost_budget=_num(cost_budget),
        priority=priority if priority in PRIORITIES else "medium", notes=notes,
    )
    tasks_db.append(task)
    return {"created": True, "task": _m(task), "count": len(tasks_for(p.id))}


def list_tasks(project_id: str, phase_key: Optional[str] = None, status: Optional[str] = None,
               assignee_id: Optional[str] = None) -> Dict[str, Any]:
    p = find_project(project_id)
    if not p:
        return {"error": f"Unknown project: {project_id}"}
    rows = tasks_for(p.id)
    if phase_key:
        rows = [t for t in rows if t.phase_key == phase_key]
    if status:
        rows = [t for t in rows if t.status == status]
    if assignee_id:
        rows = [t for t in rows if t.assignee_id == assignee_id]
    sched = {row["id"]: row for row in build_schedule(p.id).get("tasks", [])}
    out = []
    for t in rows:
        row = _m(t)
        row.update({k: sched.get(t.id, {}).get(k) for k in
                    ("planned_start", "planned_finish", "float_days", "is_critical")})
        out.append(row)
    return {"count": len(out), "tasks": out}


def update_task(task_id: str, **fields: Any) -> Dict[str, Any]:
    t = find_task(task_id)
    if not t:
        return {"error": f"Unknown task: {task_id}"}
    allowed = {"name", "phase_key", "assignee_id", "duration_days", "predecessors",
               "progress_pct", "status", "priority", "weight", "cost_budget",
               "actual_start", "actual_finish", "notes", "wbs"}
    applied: Dict[str, Any] = {}
    for key, value in fields.items():
        if key not in allowed or value is None:
            continue
        if key in ("actual_start", "actual_finish"):
            value = _iso(value)
        elif key in ("duration_days",):
            value = max(1, int(value))
        elif key in ("progress_pct", "weight", "cost_budget"):
            value = _num(value)
        setattr(t, key, value)
        applied[key] = value
    if "progress_pct" in applied:
        t.progress_pct = _clamp(t.progress_pct, 0.0, 100.0)
        if t.progress_pct >= 100.0 and "status" not in applied:
            t.status = "done"
        elif t.progress_pct > 0 and t.status == "not_started":
            t.status = "in_progress"
    if t.status == "done" and "progress_pct" not in applied:
        t.progress_pct = 100.0
    t.updated_at = _now()
    return {"updated": applied, "task": _m(t)}


def delete_task(task_id: str) -> Dict[str, Any]:
    t = find_task(task_id)
    if not t:
        return {"error": f"Unknown task: {task_id}"}
    tasks_db.remove(t)
    allocations_db[:] = [a for a in allocations_db if a.task_id != task_id]
    for other in tasks_db:
        if task_id in other.predecessors:
            other.predecessors = [p for p in other.predecessors if p != task_id]
    return {"deleted": True, "id": task_id}


def _phase_progress(ph: PmPhase) -> float:
    rows = [t for t in tasks_db if t.project_id == ph.project_id and t.phase_key == ph.key]
    return _weighted_progress(rows)


# ============================================================
# SCHEDULING
# ============================================================


def _weighted_progress(rows: List[PmTask]) -> float:
    if not rows:
        return 0.0
    total = sum(_task_weight(t) for t in rows) or 1.0
    done = sum(_task_weight(t) * _clamp(t.progress_pct, 0.0, 100.0) for t in rows)
    return _round(done / total, 2)


def _task_weight(t: PmTask) -> float:
    return t.weight if t.weight and t.weight > 0 else float(max(1, t.duration_days or 1))


def build_schedule(project_id: str, start_date: Optional[str] = None) -> Dict[str, Any]:
    """Forward/backward pass over the task network: ES/EF, LS/LF, float, critical path."""
    p = find_project(project_id)
    if not p:
        return {"error": f"Unknown project: {project_id}"}
    tasks = tasks_for(p.id)
    if not tasks:
        return {"project_id": p.id, "start": None, "finish": None, "duration_days": 0,
                "tasks": [], "critical_path": [], "cycles": []}

    by_id = {t.id: t for t in tasks}
    preds: Dict[str, List[str]] = {}
    succs: Dict[str, List[str]] = {t.id: [] for t in tasks}
    for t in tasks:
        valid = [pid for pid in t.predecessors if pid in by_id and pid != t.id]
        preds[t.id] = valid
        for pid in valid:
            succs[pid].append(t.id)

    indeg = {t.id: len(preds[t.id]) for t in tasks}
    queue = [tid for tid, n in indeg.items() if n == 0]
    order: List[str] = []
    while queue:
        tid = queue.pop(0)
        order.append(tid)
        for s in succs[tid]:
            indeg[s] -= 1
            if indeg[s] == 0:
                queue.append(s)
    cycles = [t.id for t in tasks if t.id not in order]

    proj_start = _next_workday(_as_date(start_date or p.start_date))
    es: Dict[str, date] = {}
    ef: Dict[str, date] = {}
    for tid in order:
        dur = max(1, int(by_id[tid].duration_days or 1))
        if preds[tid] and all(pp in ef for pp in preds[tid]):
            start = max(add_working_days(ef[pp], 1) for pp in preds[tid])
        else:
            start = proj_start
        es[tid] = start
        ef[tid] = add_working_days(start, dur - 1)

    proj_finish = max(ef.values()) if ef else proj_start
    if p.end_date:
        proj_finish = max(proj_finish, _as_date(p.end_date))
    ls: Dict[str, date] = {}
    lf: Dict[str, date] = {}
    for tid in reversed(order):
        dur = max(1, int(by_id[tid].duration_days or 1))
        valid_succ = [s for s in succs[tid] if s in ls]
        if valid_succ:
            fin = min(add_working_days(ls[s], -1) for s in valid_succ)
        else:
            fin = proj_finish
        lf[tid] = fin
        ls[tid] = add_working_days(fin, -(dur - 1))

    rows = []
    for tid in order:
        t = by_id[tid]
        float_days = working_days_between(es[tid], ls[tid])
        rows.append({
            "id": tid, "wbs": t.wbs, "name": t.name, "phase_key": t.phase_key,
            "duration_days": t.duration_days, "progress_pct": t.progress_pct,
            "status": t.status, "assignee_id": t.assignee_id,
            "predecessors": preds[tid],
            "planned_start": es[tid].isoformat(), "planned_finish": ef[tid].isoformat(),
            "late_start": ls[tid].isoformat(), "late_finish": lf[tid].isoformat(),
            "float_days": float_days,
            "is_critical": float_days == 0 and t.status != "done",
            "actual_start": t.actual_start, "actual_finish": t.actual_finish,
            "weight": _task_weight(t),
        })
    rows.sort(key=lambda r: (r["planned_start"], r["name"]))
    critical = [r["id"] for r in rows if r["is_critical"]]
    duration_days = working_days_between(proj_start, proj_finish) + 1
    return {
        "project_id": p.id, "start": proj_start.isoformat(), "finish": proj_finish.isoformat(),
        "duration_days": duration_days,
        "calendar_days": (proj_finish - proj_start).days + 1,
        "task_count": len(rows), "tasks": rows, "critical_path": critical, "cycles": cycles,
        "note": "Six-day (Mon–Sat) working week; dates are earliest/latest (ES/EF, LS/LF).",
    }


def critical_path(project_id: str) -> Dict[str, Any]:
    sched = build_schedule(project_id)
    if "error" in sched:
        return sched
    rows = {r["id"]: r for r in sched["tasks"]}
    chain = [rows[cid] for cid in sched["critical_path"] if cid in rows]
    return {"project_id": sched["project_id"], "start": sched["start"], "finish": sched["finish"],
            "duration_days": sched["duration_days"], "critical_count": len(chain),
            "critical_path": [{"wbs": r["wbs"], "name": r["name"], "start": r["planned_start"],
                               "finish": r["planned_finish"], "duration_days": r["duration_days"]}
                              for r in chain],
            "cycles": sched["cycles"]}


def gantt(project_id: str) -> Dict[str, Any]:
    """Gantt-ready rows grouped by phase."""
    sched = build_schedule(project_id)
    if "error" in sched:
        return sched
    phase_names = {ph.key: ph.name for ph in phases_for(project_id)}
    rows = []
    for r in sched["tasks"]:
        rows.append({
            "phase": phase_names.get(r["phase_key"], r["phase_key"] or "—"),
            "task": r["name"], "wbs": r["wbs"], "start": r["planned_start"],
            "finish": r["planned_finish"], "duration_days": r["duration_days"],
            "progress_pct": r["progress_pct"], "is_critical": r["is_critical"],
            "float_days": r["float_days"],
        })
    return {"project_id": project_id, "start": sched["start"], "finish": sched["finish"],
            "critical_count": len(sched["critical_path"]), "rows": rows}


# ============================================================
# PROGRESS, COST & EARNED VALUE
# ============================================================


def record_progress(project_id: str, percent: float, note: Optional[str] = None,
                    by: Optional[str] = None, manpower: int = 0,
                    weather: Optional[str] = None, on: Optional[str] = None) -> Dict[str, Any]:
    p = find_project(project_id)
    if not p:
        return {"error": f"Unknown project: {project_id}"}
    rec = PmProgressUpdate(
        project_id=p.id, date=_iso(on, _today()), percent=_clamp(_num(percent), 0.0, 100.0),
        note=note, by=by, manpower=int(manpower), weather=weather,
    )
    progress_updates_db.append(rec)
    if p.status == "planning" and rec.percent > 0:
        p.status = "active"
    p.updated_at = _now()
    return {"recorded": True, "update": _m(rec), "actual_pct": project_progress(p.id)["actual_pct"]}


def progress_history(project_id: str) -> Dict[str, Any]:
    p = find_project(project_id)
    if not p:
        return {"error": f"Unknown project: {project_id}"}
    rows = sorted([u for u in progress_updates_db if u.project_id == p.id], key=lambda u: u.date)
    return {"project_id": p.id, "count": len(rows),
            "updates": [_m(u) for u in rows],
            "latest": _m(rows[-1]) if rows else None,
            "actual_pct": project_progress(p.id)["actual_pct"]}


def project_progress(project_id: str) -> Dict[str, Any]:
    p = find_project(project_id)
    if not p:
        return {"error": f"Unknown project: {project_id}"}
    tasks = tasks_for(p.id)
    actual = _weighted_progress(tasks)
    sched = build_schedule(p.id)
    planned = planned_progress(p.id)["planned_pct"] if tasks else 0.0
    by_status: Dict[str, int] = {}
    for t in tasks:
        by_status[t.status] = by_status.get(t.status, 0) + 1
    return {"project_id": p.id, "actual_pct": actual, "planned_pct": planned,
            "variance_pct": _round(actual - planned, 2),
            "tasks": len(tasks), "by_status": by_status,
            "milestones_met": sum(1 for m in milestones_for(p.id) if m.status == "met"),
            "schedule_finish": sched.get("finish")}


def planned_progress(project_id: str, as_of: Optional[str] = None) -> Dict[str, Any]:
    p = find_project(project_id)
    if not p:
        return {"error": f"Unknown project: {project_id}"}
    cutoff = _as_date(as_of, _today())
    sched = build_schedule(p.id)
    rows = sched.get("tasks", [])
    total = sum(r["weight"] for r in rows) or 1.0
    earned = 0.0
    for r in rows:
        s, f = _as_date(r["planned_start"]), _as_date(r["planned_finish"])
        if cutoff >= f:
            frac = 1.0
        elif cutoff <= s:
            frac = 0.0
        else:
            span = max(1, working_days_between(s, f) + 1)
            frac = _clamp(working_days_between(s, cutoff) / span, 0.0, 1.0)
        earned += r["weight"] * frac
    return {"project_id": p.id, "as_of": cutoff.isoformat(),
            "planned_pct": _round(earned / total * 100.0, 2)}


def s_curve(project_id: str, weeks: int = 52) -> Dict[str, Any]:
    """Weekly planned vs actual cumulative completion."""
    p = find_project(project_id)
    if not p:
        return {"error": f"Unknown project: {project_id}"}
    sched = build_schedule(p.id)
    rows = sched.get("tasks", [])
    if not rows:
        return {"project_id": p.id, "weeks": [], "series": {"planned": [], "actual": []}}
    start = _as_date(sched["start"])
    finish = _as_date(sched["finish"])
    total = sum(r["weight"] for r in rows) or 1.0
    actual_now = _weighted_progress(tasks_for(p.id))
    today = _today()
    points: List[Tuple[str, float, float]] = []
    cursor = start
    step = timedelta(days=7)
    i = 0
    while cursor <= finish and i <= weeks:
        planned = sum(r["weight"] * _planned_frac(r, cursor) for r in rows) / total * 100.0
        if cursor <= today:
            span = max(1, working_days_between(start, today))
            frac = _clamp(working_days_between(start, min(cursor, today)) / span, 0.0, 1.0)
            actual = actual_now * frac
        else:
            actual = actual_now
        points.append((cursor.isoformat(), _round(planned, 2), _round(actual, 2)))
        cursor = cursor + step
        i += 1
    return {"project_id": p.id, "start": sched["start"], "finish": sched["finish"],
            "weeks": [{"week": d, "planned_pct": pl, "actual_pct": ac} for d, pl, ac in points],
            "series": {"planned": [pl for _, pl, _ in points],
                       "actual": [ac for _, _, ac in points]},
            "labels": [d for d, _, _ in points]}


def _planned_frac(row: Dict[str, Any], cutoff: date) -> float:
    s, f = _as_date(row["planned_start"]), _as_date(row["planned_finish"])
    if cutoff >= f:
        return 1.0
    if cutoff <= s:
        return 0.0
    span = max(1, working_days_between(s, f) + 1)
    return _clamp(working_days_between(s, cutoff) / span, 0.0, 1.0)


def add_cost(project_id: str, amount: float, category: str = "other",
             description: str = "", kind: str = "actual", date: Optional[str] = None,
             vendor: Optional[str] = None, invoice_ref: Optional[str] = None,
             recorded_by: Optional[str] = None) -> Dict[str, Any]:
    p = find_project(project_id)
    if not p:
        return {"error": f"Unknown project: {project_id}"}
    entry = PmCostEntry(
        project_id=p.id, date=_iso(date, _today()),
        category=category if category in COST_CATEGORIES else "other",
        description=description, amount=_num(amount),
        kind=kind if kind in COST_KINDS else "actual",
        vendor=vendor, invoice_ref=invoice_ref, recorded_by=recorded_by,
    )
    cost_entries_db.append(entry)
    return {"created": True, "entry": _m(entry), "count": len(costs_for(p.id))}


def list_costs(project_id: str, kind: Optional[str] = None,
               category: Optional[str] = None) -> Dict[str, Any]:
    p = find_project(project_id)
    if not p:
        return {"error": f"Unknown project: {project_id}"}
    rows = costs_for(p.id)
    if kind:
        rows = [c for c in rows if c.kind == kind]
    if category:
        rows = [c for c in rows if c.category == category]
    rows = sorted(rows, key=lambda c: c.date)
    return {"count": len(rows), "entries": [_m(c) for c in rows],
            "total": _round(sum(c.amount for c in rows))}


def approved_change_cost(project_id: str) -> float:
    return _round(sum(c.cost_impact for c in changes_for(project_id) if c.status == "approved"))


def approved_change_days(project_id: str) -> int:
    return int(sum(c.schedule_impact_days for c in changes_for(project_id) if c.status == "approved"))


def cost_status(project_id: str) -> Dict[str, Any]:
    p = find_project(project_id)
    if not p:
        return {"error": f"Unknown project: {project_id}"}
    entries = costs_for(p.id)
    approved_cost = approved_change_cost(p.id)
    revised = _round(p.budget)   # budget is the current/revised figure (baseline + approved changes)
    actual = _round(sum(c.amount for c in entries if c.kind == "actual"))
    committed = _round(sum(c.amount for c in entries if c.kind == "committed"))
    by_category: Dict[str, Dict[str, float]] = {}
    for c in entries:
        row = by_category.setdefault(c.category, {"actual": 0.0, "committed": 0.0})
        row[c.kind if c.kind in ("actual", "committed") else "actual"] += c.amount
    prog = project_progress(p.id)["actual_pct"] / 100.0
    forecast = revised if prog <= 0 else _round(max(actual + committed, actual / max(prog, 0.01)))
    variance = _round(revised - forecast)
    return {
        "project_id": p.id, "baseline_budget": _round(p.baseline_budget or p.budget),
        "approved_changes": approved_cost, "revised_budget": revised,
        "contract_value": _round(p.contract_value),
        "actual_cost": actual, "committed_cost": committed,
        "exposure": _round(max(actual, actual + committed)),
        "forecast_to_complete": _round(max(0.0, forecast - actual)),
        "forecast_final": forecast,
        "variance_at_completion": variance,
        "spent_pct": _round(actual / revised * 100.0) if revised else 0.0,
        "by_category": {k: {kk: _round(vv) for kk, vv in v.items()} for k, v in sorted(by_category.items())},
    }


def earned_value(project_id: str, as_of: Optional[str] = None) -> Dict[str, Any]:
    """Full earned-value analysis: PV, EV, AC, variances, indices, EAC family."""
    p = find_project(project_id)
    if not p:
        return {"error": f"Unknown project: {project_id}"}
    budget = _round(p.budget)   # current/revised budget (baseline + approved changes)
    planned_pct = planned_progress(p.id, as_of)["planned_pct"]
    actual_pct = project_progress(p.id)["actual_pct"]
    pv = _round(budget * planned_pct / 100.0)
    ev = _round(budget * actual_pct / 100.0)
    ac = _round(sum(c.amount for c in costs_for(p.id) if c.kind == "actual"))
    sv = _round(ev - pv)
    cv = _round(ev - ac)
    spi = _round(ev / pv, 4) if pv else None
    cpi = _round(ev / ac, 4) if ac else None
    method = PMO_CONFIG["eac_method"]
    if method == "budget" or cpi in (None, 0):
        eac = budget
    elif method == "composite" and spi and cpi:
        eac = _round(ac + (budget - ev) / (cpi * spi))
    else:
        eac = _round(budget / cpi) if cpi else budget
    etc = _round(max(0.0, eac - ac))
    vac = _round(budget - eac)
    tcpi = _round((budget - ev) / (budget - ac), 4) if (budget - ac) else None
    return {
        "project_id": p.id, "as_of": _as_date(as_of, _today()).isoformat(),
        "currency": p.currency, "budget": budget,
        "planned_pct": planned_pct, "actual_pct": actual_pct,
        "PV": pv, "EV": ev, "AC": ac,
        "SV": sv, "CV": cv, "SPI": spi, "CPI": cpi,
        "EAC": eac, "ETC": etc, "VAC": vac, "TCPI": tcpi,
        "performance": {
            "schedule": "ahead" if (spi or 0) > 1.02 else "behind" if (spi or 1) < 0.98 else "on_track",
            "cost": "under" if (cpi or 0) > 1.02 else "over" if (cpi or 1) < 0.98 else "on_budget",
        },
        "eac_method": method,
    }


def kpi(project_id: str) -> Dict[str, Any]:
    """A scorecard of the headline KPIs for a project."""
    p = find_project(project_id)
    if not p:
        return {"error": f"Unknown project: {project_id}"}
    evm = earned_value(p.id)
    health = project_health(p.id)
    prog = project_progress(p.id)
    cost = cost_status(p.id)
    milestones = milestones_for(p.id)
    risks = [r for r in risks_for(p.id) if r.status != "closed"]
    return {
        "project_id": p.id, "name": p.name, "health": health["overall"],
        "schedule_performance_index": evm["SPI"], "cost_performance_index": evm["CPI"],
        "progress_pct": prog["actual_pct"], "planned_pct": prog["planned_pct"],
        "spent_pct": cost["spent_pct"], "budget_variance": cost["variance_at_completion"],
        "milestones_total": len(milestones),
        "milestones_met": sum(1 for m in milestones if m.status == "met"),
        "milestones_at_risk": sum(1 for m in milestones if m.status == "at_risk"),
        "open_risks": len(risks),
        "high_risks": sum(1 for r in risks if r.probability * r.impact >= 10),
        "open_changes": sum(1 for c in changes_for(p.id) if c.status in ("draft", "submitted")),
        "open_actions": sum(1 for a in actions_db
                            if a.project_id == p.id and a.status == "open"),
        "critical_tasks": len([t for t in tasks_for(p.id) if t.status not in ("done",)]),
    }


# ============================================================
# MONITORING: HEALTH & ALERTS
# ============================================================


def project_health(project_id: str) -> Dict[str, Any]:
    """Schedule/cost/risk/quality RAG status plus an overall band."""
    p = find_project(project_id)
    if not p:
        return {"error": f"Unknown project: {project_id}"}
    evm = earned_value(p.id)
    slip = _schedule_slip_days(p.id)
    prog = project_progress(p.id)
    cost = cost_status(p.id)

    spi = evm["SPI"] if evm["SPI"] is not None else 1.0
    cpi = evm["CPI"] if evm["CPI"] is not None else 1.0
    started = (evm["EV"] > 0 or evm["AC"] > 0
               or any(u.project_id == p.id for u in progress_updates_db))

    # Schedule RAG
    if not started:
        schedule = "green"
    elif spi >= PMO_CONFIG["spi_green"] and slip <= PMO_CONFIG["slip_amber_days"]:
        schedule = "green"
    elif spi >= PMO_CONFIG["spi_amber"] and slip <= PMO_CONFIG["slip_red_days"]:
        schedule = "amber"
    else:
        schedule = "red"

    # Cost RAG
    overrun_pct = 0.0
    if cost["revised_budget"]:
        overrun_pct = (cost["forecast_final"] - cost["revised_budget"]) / cost["revised_budget"] * 100.0
    if not started:
        cost_band = "green"
    elif cpi >= PMO_CONFIG["cpi_green"] and overrun_pct <= PMO_CONFIG["cost_overrun_amber_pct"]:
        cost_band = "green"
    elif cpi >= PMO_CONFIG["cpi_amber"] and overrun_pct <= PMO_CONFIG["cost_overrun_red_pct"]:
        cost_band = "amber"
    else:
        cost_band = "red"

    # Risk RAG
    open_risks = [r for r in risks_for(p.id) if r.status != "closed"]
    max_risk = max((r.probability * r.impact for r in open_risks), default=0)
    if max_risk >= PMO_CONFIG["risk_red_score"]:
        risk_band_rag = "red"
    elif max_risk >= PMO_CONFIG["risk_amber_score"]:
        risk_band_rag = "amber"
    else:
        risk_band_rag = "green"

    # Quality RAG
    q = quality_index(p.id)
    if q["score"] >= PMO_CONFIG["quality_green"]:
        quality = "green"
    elif q["score"] >= PMO_CONFIG["quality_amber"]:
        quality = "amber"
    else:
        quality = "red"

    overall = _worst(schedule, cost_band, risk_band_rag, quality)
    return {
        "project_id": p.id, "name": p.name, "status": p.status,
        "overall": overall,
        "bands": {"schedule": schedule, "cost": cost_band, "risk": risk_band_rag, "quality": quality},
        "colors": {k: RAG_COLORS[v] for k, v in
                   {"overall": overall, "schedule": schedule, "cost": cost_band,
                    "risk": risk_band_rag, "quality": quality}.items()},
        "schedule_slip_days": slip, "spi": evm["SPI"] if started else None,
        "cpi": evm["CPI"] if started else None, "started": started,
        "progress_pct": prog["actual_pct"], "planned_pct": prog["planned_pct"],
        "cost_overrun_pct": _round(overrun_pct), "max_open_risk_score": max_risk,
        "quality_index": q["score"], "verdict": _health_verdict(overall),
    }


def _health_verdict(band: str) -> str:
    return {"green": "On track — protect the plan",
            "amber": "Watch — corrective action recommended",
            "red": "Action required — escalate to the sponsor"}.get(band, "Unknown")


def _schedule_slip_days(project_id: str) -> int:
    p = find_project(project_id)
    if not p:
        return 0
    sched = build_schedule(project_id)
    if not sched.get("finish"):
        return 0
    baseline_end = p.baseline_end or p.end_date
    if not baseline_end:
        return 0
    return max(0, working_days_between(baseline_end, sched["finish"]))


def alerts(project_id: Optional[str] = None) -> Dict[str, Any]:
    """Exception-based alerts across one project or the whole portfolio."""
    projects = [find_project(project_id)] if project_id else list(projects_db)
    projects = [p for p in projects if p]
    out: List[Dict[str, Any]] = []
    today = _today()
    for p in projects:
        sched = build_schedule(p.id)
        rows = {r["id"]: r for r in sched.get("tasks", [])}
        for t in tasks_for(p.id):
            row = rows.get(t.id, {})
            finish = row.get("planned_finish")
            if t.status != "done" and finish and _as_date(finish) < today:
                out.append({"level": "red", "kind": "overdue_task", "project_id": p.id,
                            "project": p.name, "ref": t.id, "message":
                            f"Task '{t.name}' overdue since {finish} "
                            f"({working_days_between(finish, today)} working days)"})
            elif t.status == "blocked":
                out.append({"level": "amber", "kind": "blocked_task", "project_id": p.id,
                            "project": p.name, "ref": t.id,
                            "message": f"Task '{t.name}' is blocked"})
        for m in milestones_for(p.id):
            if m.status in ("pending", "at_risk") and m.planned_date:
                if _as_date(m.planned_date) < today:
                    out.append({"level": "red", "kind": "milestone_missed", "project_id": p.id,
                                "project": p.name, "ref": m.id,
                                "message": f"Milestone '{m.name}' due {m.planned_date} not met"})
                elif working_days_between(today, m.planned_date) <= 5:
                    out.append({"level": "amber", "kind": "milestone_due", "project_id": p.id,
                                "project": p.name, "ref": m.id,
                                "message": f"Milestone '{m.name}' due {m.planned_date}"})
        health = project_health(p.id)
        if health["bands"]["cost"] != "green":
            out.append({"level": health["bands"]["cost"], "kind": "cost_pressure",
                        "project_id": p.id, "project": p.name, "ref": p.id,
                        "message": f"Cost index CPI={health['cpi']} "
                                   f"(overrun {health['cost_overrun_pct']}%)"})
        if health["bands"]["schedule"] != "green":
            out.append({"level": health["bands"]["schedule"], "kind": "schedule_pressure",
                        "project_id": p.id, "project": p.name, "ref": p.id,
                        "message": f"Schedule index SPI={health['spi']}, slip "
                                   f"{health['schedule_slip_days']} days"})
        for r in risks_for(p.id):
            if r.status != "closed" and r.probability * r.impact >= PMO_CONFIG["risk_red_score"]:
                out.append({"level": "red", "kind": "high_risk", "project_id": p.id,
                            "project": p.name, "ref": r.id,
                            "message": f"High risk: {r.title} ({risk_band(r.probability * r.impact)})"})
        for w in work_orders_overdue(p.id):
            out.append({"level": "amber", "kind": "action_overdue", "project_id": p.id,
                        "project": p.name, "ref": w.id,
                        "message": f"Action '{w.title}' overdue since {w.due_on}"})
        last = max([u.date for u in progress_updates_db if u.project_id == p.id], default=None)
        if p.status == "active" and last:
            if working_days_between(last, today) > PMO_CONFIG["stale_progress_days"]:
                out.append({"level": "amber", "kind": "stale_progress", "project_id": p.id,
                            "project": p.name, "ref": p.id,
                            "message": f"No progress update since {last}"})
        elif p.status == "active" and not last:
            out.append({"level": "amber", "kind": "no_progress", "project_id": p.id,
                        "project": p.name, "ref": p.id,
                        "message": "Active project has no progress updates"})

    order = {"red": 0, "amber": 1}
    out.sort(key=lambda a: order.get(a["level"], 2))
    return {"count": len(out), "red": sum(1 for a in out if a["level"] == "red"),
            "amber": sum(1 for a in out if a["level"] == "amber"),
            "scope": project_id or "portfolio", "alerts": out}


def work_orders_overdue(project_id: str) -> List[PmAction]:
    today = _today()
    return [a for a in actions_db
            if a.project_id == project_id and a.status == "open" and a.due_on
            and _as_date(a.due_on) < today]


def quality_index(project_id: str) -> Dict[str, Any]:
    rows = [i for i in inspections_db if i.project_id == project_id]
    items = [it for i in rows for it in i.checklist]
    scored = [it for it in items if it.result in ("pass", "fail")]
    passed = sum(1 for it in scored if it.result == "pass")
    score = _round(passed / len(scored) * 100.0) if scored else 100.0
    return {"project_id": project_id, "inspections": len(rows), "items": len(items),
            "scored": len(scored), "passed": passed, "score": score,
            "failures": [{"inspection": i.title, "item": it.item, "note": it.note}
                         for i in rows for it in i.checklist if it.result == "fail"]}


def monitoring_snapshot(project_id: str) -> Dict[str, Any]:
    """Everything a project-controls meeting needs, in one call."""
    p = find_project(project_id)
    if not p:
        return {"error": f"Unknown project: {project_id}"}
    return {
        "project": _m(p),
        "health": project_health(p.id),
        "kpi": kpi(p.id),
        "progress": project_progress(p.id),
        "cost": cost_status(p.id),
        "evm": earned_value(p.id),
        "schedule": {k: build_schedule(p.id)[k] for k in
                     ("start", "finish", "duration_days", "critical_path", "cycles")},
        "milestones": [_milestone_view(m) for m in milestones_for(p.id)],
        "alerts": alerts(p.id)["alerts"],
        "resources": resource_load(project_id=p.id)["resources"],
        "risks": ["%s" % r.title for r in risks_for(p.id) if r.status != "closed"],
        "generated_at": _now(),
    }


def portfolio_dashboard() -> Dict[str, Any]:
    """Rolled-up view across every running project."""
    total_budget = 0.0
    total_actual = 0.0
    total_ev = 0.0
    total_pv = 0.0
    by_status: Dict[str, int] = {}
    by_health: Dict[str, int] = {"green": 0, "amber": 0, "red": 0}
    rows = []
    for p in projects_db:
        health = project_health(p.id)
        evm = earned_value(p.id)
        cost = cost_status(p.id)
        prog = project_progress(p.id)
        by_status[p.status] = by_status.get(p.status, 0) + 1
        by_health[health["overall"]] = by_health.get(health["overall"], 0) + 1
        total_budget += cost["revised_budget"]
        total_actual += cost["actual_cost"]
        total_ev += evm["EV"]
        total_pv += evm["PV"]
        rows.append({"id": p.id, "code": p.code, "name": p.name, "status": p.status,
                     "project_type": p.project_type, "city": p.city,
                     "progress_pct": prog["actual_pct"], "health": health["overall"],
                     "budget": cost["revised_budget"], "actual_cost": cost["actual_cost"],
                     "SPI": evm["SPI"], "CPI": evm["CPI"]})
    rows.sort(key=lambda r: {"red": 0, "amber": 1, "green": 2}.get(r["health"], 3))
    return {
        "projects": len(projects_db), "by_status": by_status, "by_health": by_health,
        "financials": {"total_budget": _round(total_budget), "total_actual": _round(total_actual),
                       "total_committed": _round(sum(c.amount for c in cost_entries_db
                                                     if c.kind == "committed"))},
        "portfolio_spi": _round(total_ev / total_pv, 4) if total_pv else None,
        "portfolio_cpi": _round(total_ev / total_actual, 4) if total_actual else None,
        "resources": len(resources_db), "open_risks": sum(1 for r in risks_db if r.status != "closed"),
        "alerts": alerts()["count"], "rows": rows,
    }


# ============================================================
# RESOURCES
# ============================================================


def add_resource(name: str, role: str = "engineer", trade: Optional[str] = None,
                 day_rate: float = 0.0, capacity_pct: float = 100.0,
                 skills: Optional[List[str]] = None, contact: Optional[str] = None) -> Dict[str, Any]:
    res = PmResource(name=name, role=role, trade=trade, day_rate=_num(day_rate),
                     capacity_pct=_num(capacity_pct, 100.0), skills=list(skills or []),
                     contact=contact)
    resources_db.append(res)
    return {"created": True, "resource": _m(res), "count": len(resources_db)}


def list_resources(trade: Optional[str] = None, active_only: bool = False) -> Dict[str, Any]:
    rows = list(resources_db)
    if trade:
        rows = [r for r in rows if r.trade == trade]
    if active_only:
        rows = [r for r in rows if r.active]
    return {"count": len(rows), "resources": [_m(r) for r in rows],
            "trades": sorted({r.trade for r in resources_db if r.trade})}


def assign(task_id: str, resource_id: str, units_pct: float = 100.0,
           notes: Optional[str] = None) -> Dict[str, Any]:
    task = find_task(task_id)
    if not task:
        return {"error": f"Unknown task: {task_id}"}
    res = find_resource(resource_id)
    if not res:
        return {"error": f"Unknown resource: {resource_id}",
                "resources": [{"id": r.id, "name": r.name} for r in resources_db]}
    alloc = PmAllocation(project_id=task.project_id, task_id=task_id, resource_id=resource_id,
                         units_pct=_num(units_pct, 100.0), notes=notes)
    allocations_db.append(alloc)
    if not task.assignee_id:
        task.assignee_id = resource_id
    return {"created": True, "allocation": _m(alloc)}


def resource_load(project_id: Optional[str] = None, window_start: Optional[str] = None,
                  window_end: Optional[str] = None) -> Dict[str, Any]:
    """Planned utilisation per resource over a window, with over-allocation flags."""
    projects = [find_project(project_id)] if project_id else list(projects_db)
    projects = [p for p in projects if p]
    load: Dict[str, Dict[str, Any]] = {}
    for p in projects:
        sched = {r["id"]: r for r in build_schedule(p.id).get("tasks", [])}
        for a in [x for x in allocations_db if x.project_id == p.id]:
            row = sched.get(a.task_id)
            if not row:
                continue
            start = _as_date(window_start, _as_date(row["planned_start"]))
            end = _as_date(window_end, _as_date(row["planned_finish"]))
            if window_start and _as_date(row["planned_finish"]) < _as_date(window_start):
                continue
            if window_end and _as_date(row["planned_start"]) > _as_date(window_end):
                continue
            res = find_resource(a.resource_id)
            entry = load.setdefault(a.resource_id, {
                "resource_id": a.resource_id, "name": res.name if res else a.resource_id,
                "role": res.role if res else None, "trade": res.trade if res else None,
                "capacity_pct": res.capacity_pct if res else 100.0,
                "planned_pct": 0.0, "tasks": []})
            entry["planned_pct"] += a.units_pct
            entry["tasks"].append({"project_id": p.id, "task": row["name"],
                                   "units_pct": a.units_pct, "start": start.isoformat(),
                                   "end": end.isoformat()})
    rows = []
    for entry in load.values():
        capacity = entry["capacity_pct"] or 100.0
        entry["utilisation_pct"] = _round(entry["planned_pct"] / capacity * 100.0)
        entry["over_allocated"] = entry["planned_pct"] > capacity
        entry["planned_pct"] = _round(entry["planned_pct"])
        rows.append(entry)
    rows.sort(key=lambda r: -r["planned_pct"])
    return {"count": len(rows), "over_allocated": sum(1 for r in rows if r["over_allocated"]),
            "resources": rows}


# ============================================================
# RAID, SITE, CHANGE, QUALITY, ACTIONS
# ============================================================


def add_risk(project_id: str, title: str, kind: str = "risk", probability: int = 3,
             impact: int = 3, description: Optional[str] = None, category: Optional[str] = None,
             owner: Optional[str] = None, mitigation: Optional[str] = None,
             due_on: Optional[str] = None) -> Dict[str, Any]:
    p = find_project(project_id)
    if not p:
        return {"error": f"Unknown project: {project_id}"}
    r = PmRisk(
        project_id=p.id, kind=kind if kind in RAID_KINDS else "risk", title=title,
        description=description, category=category, owner=owner, mitigation=mitigation,
        probability=int(_clamp(_num(probability, 3), 1, 5)),
        impact=int(_clamp(_num(impact, 3), 1, 5)), due_on=_iso(due_on),
    )
    risks_db.append(r)
    return {"created": True, "risk": {**_m(r), "score": r.probability * r.impact,
                                      "band": risk_band(r.probability * r.impact)}}


def list_risks(project_id: Optional[str] = None, kind: Optional[str] = None,
               status: Optional[str] = None, min_score: int = 0) -> Dict[str, Any]:
    rows = list(risks_db)
    if project_id:
        p = find_project(project_id)
        rows = [r for r in rows if p and r.project_id == p.id]
    if kind:
        rows = [r for r in rows if r.kind == kind]
    if status:
        rows = [r for r in rows if r.status == status]
    rows = [r for r in rows if r.probability * r.impact >= min_score]
    rows.sort(key=lambda r: -(r.probability * r.impact))
    return {"count": len(rows), "risks": [
        {**_m(r), "score": r.probability * r.impact,
         "band": risk_band(r.probability * r.impact)} for r in rows]}


def update_risk(risk_id: str, **fields: Any) -> Dict[str, Any]:
    r = find_risk(risk_id)
    if not r:
        return {"error": f"Unknown risk: {risk_id}"}
    allowed = {"title", "kind", "description", "category", "probability", "impact",
               "owner", "mitigation", "status", "due_on"}
    applied: Dict[str, Any] = {}
    for key, value in fields.items():
        if key not in allowed or value is None:
            continue
        if key in ("probability", "impact"):
            value = int(_clamp(_num(value, 3), 1, 5))
        elif key == "due_on":
            value = _iso(value)
        setattr(r, key, value)
        applied[key] = value
    return {"updated": applied, "risk": {**_m(r), "score": r.probability * r.impact,
                                         "band": risk_band(r.probability * r.impact)}}


def risk_matrix(project_id: Optional[str] = None) -> Dict[str, Any]:
    """A 5×5 probability × impact heat matrix with the placed RAID items."""
    p = find_project(project_id) if project_id else None
    rows = [r for r in risks_db if (not p or r.project_id == p.id) and r.status != "closed"]
    grid: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        key = f"{r.probability}x{r.impact}"
        grid.setdefault(key, []).append({"id": r.id, "title": r.title, "kind": r.kind,
                                         "score": r.probability * r.impact,
                                         "band": risk_band(r.probability * r.impact)})
    counts: Dict[str, int] = {}
    for r in rows:
        b = risk_band(r.probability * r.impact)
        counts[b] = counts.get(b, 0) + 1
    return {"project_id": p.id if p else None, "count": len(rows), "by_band": counts,
            "cells": grid, "bands": {k: list(v) for k, v in RISK_BANDS.items()}}


def log_site_day(project_id: str, date: Optional[str] = None, weather: Optional[str] = None,
                 manpower: int = 0, equipment: Optional[List[str]] = None,
                 work_done: Optional[str] = None, issues: Optional[str] = None,
                 safety_incidents: int = 0, visitors: Optional[str] = None,
                 photos: Optional[List[str]] = None, by: Optional[str] = None) -> Dict[str, Any]:
    p = find_project(project_id)
    if not p:
        return {"error": f"Unknown project: {project_id}"}
    log = PmSiteLog(
        project_id=p.id, date=_iso(date, _today()), weather=weather, manpower=int(manpower),
        equipment=list(equipment or []), work_done=work_done, issues=issues,
        safety_incidents=int(safety_incidents), visitors=visitors,
        photos=list(photos or []), by=by,
    )
    site_logs_db.append(log)
    return {"created": True, "log": _m(log), "count": len([x for x in site_logs_db
                                                           if x.project_id == p.id])}


def list_site_logs(project_id: str, limit: int = 30) -> Dict[str, Any]:
    p = find_project(project_id)
    if not p:
        return {"error": f"Unknown project: {project_id}"}
    rows = sorted([x for x in site_logs_db if x.project_id == p.id], key=lambda x: x.date, reverse=True)
    total_manpower = sum(r.manpower for r in rows[:limit])
    incidents = sum(r.safety_incidents for r in rows[:limit])
    return {"count": len(rows), "logs": [_m(r) for r in rows[:limit]],
            "manpower_total": total_manpower, "safety_incidents": incidents}


def site_report(project_id: str, on: Optional[str] = None) -> Dict[str, Any]:
    """A daily site report for a project (aggregated diary entry)."""
    p = find_project(project_id)
    if not p:
        return {"error": f"Unknown project: {project_id}"}
    target = _as_date(on, _today()).isoformat()
    row = next((x for x in site_logs_db if x.project_id == p.id and x.date == target), None)
    health = project_health(p.id)
    progress = project_progress(p.id)
    return {"project_id": p.id, "project": p.name, "date": target,
            "site_log": _m(row) if row else None,
            "progress_pct": progress["actual_pct"], "health": health["overall"],
            "open_alerts": [a for a in alerts(p.id)["alerts"]][:8],
            "weather_note": "Log the actual weather; heavy rain/work-days lost feed the delay register."}


def raise_change(project_id: str, title: str, description: Optional[str] = None,
                 reason: Optional[str] = None, cost_impact: float = 0.0,
                 schedule_impact_days: int = 0, requested_by: Optional[str] = None,
                 status: str = "submitted") -> Dict[str, Any]:
    p = find_project(project_id)
    if not p:
        return {"error": f"Unknown project: {project_id}"}
    c = PmChangeRequest(
        project_id=p.id, title=title, description=description, reason=reason,
        cost_impact=_num(cost_impact), schedule_impact_days=int(schedule_impact_days),
        requested_by=requested_by, status=status if status in CHANGE_STATUSES else "submitted",
    )
    change_requests_db.append(c)
    return {"created": True, "change": _m(c)}


def list_changes(project_id: str, status: Optional[str] = None) -> Dict[str, Any]:
    p = find_project(project_id)
    if not p:
        return {"error": f"Unknown project: {project_id}"}
    rows = changes_for(p.id)
    if status:
        rows = [c for c in rows if c.status == status]
    return {"count": len(rows), "changes": [_m(c) for c in rows],
            "approved_cost_impact": approved_change_cost(p.id),
            "approved_schedule_impact_days": approved_change_days(p.id)}


def decide_change(change_id: str, approve: bool = True, by: Optional[str] = None,
                  note: Optional[str] = None) -> Dict[str, Any]:
    c = find_change(change_id)
    if not c:
        return {"error": f"Unknown change: {change_id}"}
    c.status = "approved" if approve else "rejected"
    c.decided_by = by
    c.decided_on = _today().isoformat()
    c.decision_note = note
    p = find_project(c.project_id)
    if p and approve:
        p.budget = _round(p.budget + c.cost_impact)
        p.updated_at = _now()
    return {"change": _m(c), "project_budget": p.budget if p else None}


def add_inspection(project_id: str, title: str,
                   checklist: Optional[List[Dict[str, Any]]] = None,
                   phase_key: Optional[str] = None, area: Optional[str] = None,
                   inspector: Optional[str] = None, date: Optional[str] = None,
                   status: str = "open", notes: Optional[str] = None) -> Dict[str, Any]:
    p = find_project(project_id)
    if not p:
        return {"error": f"Unknown project: {project_id}"}
    items: List[PmChecklistItem] = []
    source = checklist
    if source is None:
        source = [{"item": f"{area or 'general'} — {a.replace('_', ' ')} compliance check"}
                  for a in (QUALITY_AREAS[:5])]
    for item in source:
        if isinstance(item, str):
            items.append(PmChecklistItem(item=item))
        else:
            items.append(PmChecklistItem(
                item=str(item.get("item", "")), result=str(item.get("result", "pending")),
                note=item.get("note")))
    insp = PmInspection(project_id=p.id, title=title, phase_key=phase_key, area=area,
                        inspector=inspector, date=_iso(date, _today()), checklist=items,
                        status=status, notes=notes)
    inspections_db.append(insp)
    return {"created": True, "inspection": _m(insp),
            "quality_index": quality_index(p.id)["score"]}


def list_inspections(project_id: str, status: Optional[str] = None) -> Dict[str, Any]:
    p = find_project(project_id)
    if not p:
        return {"error": f"Unknown project: {project_id}"}
    rows = [i for i in inspections_db if i.project_id == p.id]
    if status:
        rows = [i for i in rows if i.status == status]
    return {"count": len(rows), "inspections": [_m(i) for i in rows],
            "quality_index": quality_index(p.id)}


def add_action(project_id: str, title: str, owner: Optional[str] = None,
               due_on: Optional[str] = None, priority: str = "medium",
               meeting: Optional[str] = None, notes: Optional[str] = None) -> Dict[str, Any]:
    p = find_project(project_id)
    if not p:
        return {"error": f"Unknown project: {project_id}"}
    a = PmAction(project_id=p.id, title=title, owner=owner, due_on=_iso(due_on),
                 priority=priority if priority in PRIORITIES else "medium",
                 meeting=meeting, notes=notes)
    actions_db.append(a)
    return {"created": True, "action": _m(a)}


def list_actions(project_id: Optional[str] = None, status: Optional[str] = None) -> Dict[str, Any]:
    rows = list(actions_db)
    if project_id:
        p = find_project(project_id)
        rows = [a for a in rows if p and a.project_id == p.id]
    if status:
        rows = [a for a in rows if a.status == status]
    today = _today()
    return {"count": len(rows), "actions": [
        {**_m(a), "overdue": bool(a.due_on and a.status == "open" and _as_date(a.due_on) < today)}
        for a in rows]}


def close_action(action_id: str, status: str = "done") -> Dict[str, Any]:
    a = find_action(action_id)
    if not a:
        return {"error": f"Unknown action: {action_id}"}
    a.status = status
    return {"action": _m(a)}


# ============================================================
# REPORTS & OVERVIEW
# ============================================================


def project_report(project_id: str) -> Dict[str, Any]:
    """A full project status report as structured data."""
    p = find_project(project_id)
    if not p:
        return {"error": f"Unknown project: {project_id}"}
    return {
        "project": _m(p),
        "summary": {"health": project_health(p.id)["overall"],
                    "progress_pct": project_progress(p.id)["actual_pct"],
                    "spi": earned_value(p.id)["SPI"], "cpi": earned_value(p.id)["CPI"],
                    "budget": cost_status(p.id)["revised_budget"],
                    "forecast_final": cost_status(p.id)["forecast_final"]},
        "schedule": build_schedule(p.id),
        "progress": project_progress(p.id),
        "cost": cost_status(p.id),
        "evm": earned_value(p.id),
        "kpi": kpi(p.id),
        "milestones": [_milestone_view(m) for m in milestones_for(p.id)],
        "risks": list_risks(p.id)["risks"],
        "changes": [_m(c) for c in changes_for(p.id)],
        "quality": quality_index(p.id),
        "site_logs": list_site_logs(p.id, limit=10)["logs"],
        "actions": list_actions(p.id)["actions"],
        "alerts": alerts(p.id)["alerts"],
        "generated_at": _now(),
    }


def _s_curve_svg(series: Dict[str, List[float]], labels: List[str],
                 width: int = 680, height: int = 220) -> str:
    pad_l, pad_r, pad_t, pad_b = 34, 12, 14, 26
    iw, ih = width - pad_l - pad_r, height - pad_t - pad_b
    n = max(1, len(labels) - 1)

    def x(i: int) -> float:
        return pad_l + iw * (i / n)

    def y(v: float) -> float:
        return pad_t + ih * (1 - _clamp(v, 0, 100) / 100.0)

    def poly(pts: List[float], color: str) -> str:
        if not pts:
            return ""
        d = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(pts))
        return f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{d}"/>'

    grid = "".join(
        f'<line x1="{pad_l}" y1="{y(g):.1f}" x2="{width - pad_r}" y2="{y(g):.1f}" '
        f'stroke="#e5e7eb" stroke-width="1"/>'
        f'<text x="{pad_l - 6}" y="{y(g) + 4:.1f}" font-size="10" text-anchor="end" '
        f'fill="#6b7280">{g}</text>'
        for g in (0, 25, 50, 75, 100))
    xlabels = ""
    if labels:
        for idx in range(0, len(labels), max(1, len(labels) // 6)):
            xlabels += (f'<text x="{x(idx):.1f}" y="{height - 8}" font-size="9" '
                        f'text-anchor="middle" fill="#6b7280">{labels[idx][5:]}</text>')
    planned = poly(series.get("planned", []), "#1f6feb")
    actual = poly(series.get("actual", []), "#1b9e4b")
    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="S-curve">{grid}'
        f'{planned}{actual}{xlabels}'
        f'<text x="{pad_l}" y="{pad_t - 2}" font-size="10" fill="#1f6feb">Planned %</text>'
        f'<text x="{pad_l + 80}" y="{pad_t - 2}" font-size="10" fill="#1b9e4b">Actual %</text>'
        '</svg>'
    )


def report_html(project_id: str, lang: str = "en", theme: str = "auto") -> str:
    """Render a printable project status report (themed, bilingual chrome)."""
    p = find_project(project_id)
    if not p:
        return gis.build_report_html(title="Project", subtitle="Not found",
                                     sections=[{"kind": "text", "text": f"Unknown project: {project_id}"}],
                                     lang=lang, theme=theme)
    rep = project_report(p.id)
    health = rep["summary"]["health"]

    def money(v: float) -> str:
        return format_pkr(v)

    evm = rep["evm"]
    cards = {"kind": "cards", "heading": "Headline", "items": [
        ("Project", p.name, f"{p.code} · {PROJECT_TYPES.get(p.project_type, {}).get('label', p.project_type)}"),
        ("Status", p.status, f"priority {p.priority}"),
        ("Health", health.upper(), "overall RAG"),
        ("Progress", f"{rep['summary']['progress_pct']}%", f"planned {rep['progress']['planned_pct']}%"),
        ("SPI", str(evm["SPI"]), "schedule performance"),
        ("CPI", str(evm["CPI"]), "cost performance"),
        ("Budget", money(rep["summary"]["budget"]), "revised budget"),
        ("Forecast", money(rep["summary"]["forecast_final"]), "forecast at completion"),
    ]}
    info = {"kind": "kv", "heading": "Project", "items": [
        ("Sponsor / client", p.client or "—"), ("City", p.city or "—"),
        ("Manager", find_resource(p.manager_id).name if find_resource(p.manager_id) else "—"),
        ("Start", p.start_date or "—"),
        ("Baseline finish", p.baseline_end or p.end_date or "—"),
        ("Forecast finish", rep["schedule"].get("finish") or "—"),
        ("Duration (working days)", str(rep["schedule"].get("duration_days", 0))),
        ("Contract value", money(p.contract_value)),
        ("Actual cost", money(rep["cost"]["actual_cost"])),
        ("Committed", money(rep["cost"]["committed_cost"])),
    ]}
    curve = {"kind": "html", "heading": "S-curve (planned vs actual %)",
             "html": _s_curve_svg(s_curve(p.id)["series"], s_curve(p.id)["labels"])}
    tasks = {"kind": "table", "heading": "Tasks",
             "columns": ["WBS", "Task", "Phase", "Start", "Finish", "Days", "Float", "Progress", "Critical"],
             "rows": [[r["wbs"] or "", r["name"], r["phase_key"] or "", r["planned_start"],
                       r["planned_finish"], r["duration_days"], r["float_days"],
                       f"{r['progress_pct']:.0f}%", "yes" if r["is_critical"] else ""]
                      for r in rep["schedule"]["tasks"]]}
    milestones = {"kind": "table", "heading": "Milestones",
                  "columns": ["Milestone", "Planned", "Forecast", "Slip (d)", "Status", "Billable"],
                  "rows": [[m["name"], m["planned_date"] or "", m["forecast_date"] or "",
                            m["slip_days"], m["status"], money(m["billable_amount"])]
                           for m in rep["milestones"]]}
    costs = {"kind": "table", "heading": "Cost by category",
             "columns": ["Category", "Actual", "Committed"],
             "rows": [[k, money(v["actual"]), money(v["committed"])]
                      for k, v in rep["cost"]["by_category"].items()]}
    risks = {"kind": "table", "heading": "Risk register",
             "columns": ["Kind", "Title", "P", "I", "Score", "Band", "Status"],
             "rows": [[r["kind"], r["title"], r["probability"], r["impact"], r["score"],
                       r["band"], r["status"]] for r in rep["risks"]]}
    alerts_rows = [[a["level"].upper(), a["kind"], a["message"]] for a in rep["alerts"]]
    alerts_sec = {"kind": "table", "heading": "Alerts", "columns": ["Level", "Kind", "Message"],
                  "rows": alerts_rows} if alerts_rows else {"kind": "text", "heading": "Alerts",
                                                            "text": "No exceptions."}
    sections = [cards, info, curve, tasks, milestones, costs, risks, alerts_sec,
                {"kind": "text", "heading": "Disclaimer", "text": DISCLAIMER}]
    return gis.build_report_html(title=f"{p.name} — Status Report",
                                 subtitle=f"{p.code} · {p.city or ''} · {health.upper()}",
                                 sections=sections, ticker_html="", lang=lang, theme=theme)


def capabilities() -> Dict[str, Any]:
    cats: Dict[str, List[Dict[str, Any]]] = {}
    for c in PM_CAPABILITIES:
        cats.setdefault(c["category"], []).append(c)
    return {"count": len(PM_CAPABILITIES), "categories": sorted(cats),
            "capabilities": PM_CAPABILITIES, "by_category": cats}


def pmo_overview() -> Dict[str, Any]:
    """Counts, breakdowns and configuration for the whole PMO wing."""
    def tally(values: Any) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for v in values:
            out[v] = out.get(v, 0) + 1
        return out

    return {
        "config": PMO_CONFIG,
        "counts": {
            "project_types": len(PROJECT_TYPES), "capabilities": len(PM_CAPABILITIES),
            "projects": len(projects_db), "phases": len(phases_db), "milestones": len(milestones_db),
            "tasks": len(tasks_db), "resources": len(resources_db), "allocations": len(allocations_db),
            "cost_entries": len(cost_entries_db), "progress_updates": len(progress_updates_db),
            "risks": len(risks_db), "site_logs": len(site_logs_db),
            "change_requests": len(change_requests_db), "inspections": len(inspections_db),
            "actions": len(actions_db),
        },
        "projects_by_status": tally(p.status for p in projects_db),
        "projects_by_type": tally(p.project_type for p in projects_db),
        "risks_by_band": tally(risk_band(r.probability * r.impact) for r in risks_db),
        "cost_categories": COST_CATEGORIES, "risk_categories": RISK_CATEGORIES,
        "raid_kinds": RAID_KINDS, "quality_areas": QUALITY_AREAS,
        "statuses": PROJECT_STATUSES, "priorities": PRIORITIES,
        "disclaimer": DISCLAIMER,
    }
