"""Tools & Utilities center (framework-free).

Implements the portal's *Tools & Utilities* wing ("Tools for portal"): real-estate
calculators, a plot & construction studio, GIS/georeferencing and map-measurement
tools, CAD/plan utilities, photo geotagging, document conversion, the Pakistan &
Islamic calendar, and a reports/export studio.

Everything here is pure Python (standard library only) so the same code runs inside
the MCP server, the FastAPI layer and the tests with no extra services. Where a
capability genuinely needs a heavy or licensed dependency (GDAL/PROJ, PyMuPDF,
Pillow, Tesseract, DWG/DGN conversion) the tool returns an explicit
``requires_optional_dependency`` descriptor rather than pretending to do the work -
this follows the roadmap's own guidance about CAD/DWG licensing and document-AI
caveats. A real GPS EXIF writer/reader *is* implemented, dependency-free.

It reuses the portal's existing engines: ``accounting`` for mortgage/ROI maths,
``construction`` for build cost and material take-off, and ``gis`` for geodesic
measurement, GeoJSON/KML and map rendering.
"""

import base64
import csv
import io
import json
import math
import re
import struct
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

import accounting
import construction
import gis


TOOLS_CONFIG: Dict[str, Any] = {
    "currency": "PKR",
    "vat_rate": 0.17,
    "agent_commission_rate": 0.02,
    "default_marla_sqft": 272.25,
    "disclaimer": (
        "Indicative figures for planning and comparison. Statutory rates (stamp "
        "duty, CVT, registration, capital-gains tax) and Islamic-calendar dates "
        "change over time; confirm with the district/DC office and the official "
        "moon-sighting announcement before relying on them."
    ),
}


def _round(value: float, digits: int = 2) -> float:
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return 0.0


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _new_id(prefix: str = "") -> str:
    return prefix + uuid.uuid4().hex[:8]


# ============================================================
# UNITS & AREA CONVERSION
# ============================================================

# Square feet per one unit.
SQFT_PER_UNIT: Dict[str, float] = {
    "sqft": 1.0,
    "sqin": 1.0 / 144.0,
    "sqyd": 9.0,
    "sqm": 10.7639104167,
    "marla": 272.25,
    "kanal": 5445.0,
    "acre": 43560.0,
    "hectare": 107639.104167,
}

AREA_UNITS = ["sqft", "sqyd", "sqm", "marla", "kanal", "acre", "hectare"]

# Pakistan uses more than one "marla". Both are offered so conversions never
# silently pick the wrong standard.
MARLA_STANDARDS: Dict[str, Dict[str, Any]] = {
    "standard": {"marla_sqft": 272.25, "sqyd": 30.25,
                 "note": "30.25 sq yd - the common housing-scheme marla (Punjab)"},
    "small": {"marla_sqft": 225.0, "sqyd": 25.0,
              "note": "25 sq yd - used in some older/other schemes"},
}

# Linear length units (feet per unit) - for dimension tools.
FEET_PER_UNIT: Dict[str, float] = {
    "ft": 1.0, "in": 1.0 / 12.0, "yd": 3.0, "m": 3.280839895, "cm": 0.032808399, "km": 3280.839895,
}


def area_units() -> Dict[str, Any]:
    """The area units the converters understand, with their base factors."""
    return {"units": AREA_UNITS, "sqft_per_unit": dict(SQFT_PER_UNIT),
            "marla_standards": dict(MARLA_STANDARDS)}


def _sqft_per(unit: str, marla_sqft: float = 272.25) -> float:
    u = (unit or "sqft").lower()
    if u == "marla":
        return float(marla_sqft)
    if u == "kanal":
        return float(marla_sqft) * 20.0
    if u in SQFT_PER_UNIT:
        return SQFT_PER_UNIT[u]
    raise ValueError(f"Unknown area unit: {unit}")


def convert_area(value: float, from_unit: str = "sqft", to_unit: str = "marla",
                 marla_sqft: float = 272.25) -> Dict[str, Any]:
    """Convert between sqft / sqyd / sqm / marla / kanal / acre / hectare."""
    try:
        sqft = float(value) * _sqft_per(from_unit, marla_sqft)
        target = _sqft_per(to_unit, marla_sqft)
    except ValueError as exc:
        return {"error": str(exc), "units": AREA_UNITS}
    out = sqft / target if target else 0.0
    return {"input": {"value": _round(value, 4), "unit": from_unit},
            "result": {"value": _round(out, 4), "unit": to_unit},
            "sqft": _round(sqft, 4), "all_units": {u: _round(sqft / _sqft_per(u, marla_sqft), 4)
                                                   for u in AREA_UNITS},
            "marla_standard_sqft": marla_sqft}


def convert_area_all(value: float, from_unit: str = "sqft", marla_sqft: float = 272.25) -> Dict[str, Any]:
    """Show a quantity in every supported area unit at once."""
    try:
        sqft = float(value) * _sqft_per(from_unit, marla_sqft)
    except ValueError as exc:
        return {"error": str(exc), "units": AREA_UNITS}
    return {"input": {"value": _round(value, 4), "unit": from_unit},
            "conversions": {u: _round(sqft / _sqft_per(u, marla_sqft), 4) for u in AREA_UNITS}}


def convert_length(value: float, from_unit: str = "ft", to_unit: str = "m") -> Dict[str, Any]:
    """Convert between feet, inches, yards, metres, centimetres and kilometres."""
    f = FEET_PER_UNIT.get((from_unit or "ft").lower())
    t = FEET_PER_UNIT.get((to_unit or "m").lower())
    if f is None or t is None:
        return {"error": f"Unknown length unit", "units": sorted(FEET_PER_UNIT)}
    feet = float(value) * f
    return {"input": {"value": _round(value, 4), "unit": from_unit},
            "result": {"value": _round(feet / t, 4), "unit": to_unit},
            "feet": _round(feet, 4),
            "all_units": {u: _round(feet / factor, 4) for u, factor in FEET_PER_UNIT.items()}}


def plot_dimensions(area: float, from_unit: str = "marla", ratio: float = 2.0,
                    marla_sqft: float = 272.25) -> Dict[str, Any]:
    """Length / width / perimeter / diagonal of a rectangular plot of a given area."""
    try:
        sqft = float(area) * _sqft_per(from_unit, marla_sqft)
    except ValueError as exc:
        return {"error": str(exc), "units": AREA_UNITS}
    if ratio <= 0:
        return {"error": "ratio must be greater than zero"}
    width = math.sqrt(sqft / ratio)
    length = width * ratio
    return {"area_sqft": _round(sqft), "area": _round(area, 4), "from_unit": from_unit,
            "ratio": ratio, "length_ft": _round(length), "width_ft": _round(width),
            "length_m": _round(length / FEET_PER_UNIT["m"]), "width_m": _round(width / FEET_PER_UNIT["m"]),
            "perimeter_ft": _round(2 * (length + width)),
            "diagonal_ft": _round(math.hypot(length, width))}


# ============================================================
# REAL-ESTATE CALCULATORS
# ============================================================


def mortgage_calculator(price: float, down_payment: float = 0.0, annual_rate: Optional[float] = None,
                        years: Optional[int] = None, payments_per_year: int = 12) -> Dict[str, Any]:
    """Monthly installment for a home loan, plus total interest and cost."""
    price = float(price or 0.0)
    down = min(float(down_payment or 0.0), price)
    principal = max(0.0, price - down)
    if principal <= 0:
        return {"error": "price must exceed the down payment", "price": price, "down_payment": down}
    sched = accounting.mortgage_schedule(principal, annual_rate, years, payments_per_year)
    if "error" in sched:
        return sched
    return {
        "price": _round(price), "down_payment": _round(down),
        "down_payment_pct": _round(down / price * 100, 2) if price else 0.0,
        "loan_amount": _round(principal),
        "annual_rate": sched["annual_rate"], "years": sched["years"],
        "payments_per_year": sched["payments_per_year"],
        "monthly_payment": sched["payment"] if payments_per_year == 12 else _round(
            sched["payment"] * payments_per_year / 12),
        "periodic_payment": sched["payment"],
        "total_paid": sched["total_paid"], "total_interest": sched["total_interest"],
        "interest_share": sched["interest_share"],
        "total_cost": _round(down + sched["total_paid"]),
        "schedule": sched["schedule"], "schedule_truncated": sched["schedule_truncated"],
    }


def installment_plan(price: float, down_payment: float = 0.0, months: int = 36,
                     annual_markup: float = 0.0) -> Dict[str, Any]:
    """Developer-style installment plan: down payment, markup and monthly amount."""
    price = float(price or 0.0)
    down = min(float(down_payment or 0.0), price)
    financed = max(0.0, price - down)
    months = max(1, int(months or 1))
    markup = financed * float(annual_markup or 0.0) * (months / 12.0)
    total_payable = financed + markup
    return {"price": _round(price), "down_payment": _round(down),
            "down_payment_pct": _round(down / price * 100, 2) if price else 0.0,
            "financed": _round(financed), "months": months, "annual_markup": annual_markup,
            "markup": _round(markup), "total_payable": _round(total_payable),
            "monthly_installment": _round(total_payable / months)}


def rental_yield(price: float, monthly_rent: float, annual_costs: float = 0.0,
                 vacancy_rate: float = 0.0) -> Dict[str, Any]:
    """Gross and net rental yield with payback period."""
    price = float(price or 0.0)
    if price <= 0:
        return {"error": "price must be greater than zero"}
    gross = float(monthly_rent or 0.0) * 12.0
    effective = gross * (1 - float(vacancy_rate or 0.0))
    net = effective - float(annual_costs or 0.0)
    return {"price": _round(price), "monthly_rent": _round(monthly_rent),
            "gross_annual_rent": _round(gross),
            "vacancy_rate": vacancy_rate, "effective_annual_rent": _round(effective),
            "annual_costs": _round(annual_costs), "net_annual_income": _round(net),
            "gross_yield_pct": _round(gross / price * 100, 3),
            "net_yield_pct": _round(net / price * 100, 3),
            "payback_years": _round(price / net, 1) if net > 0 else None,
            "cap_rate_pct": _round(net / price * 100, 3)}


def appreciation_projection(current_value: float, cagr: float = 0.08, years: int = 10,
                            monthly_rent: float = 0.0, rent_growth: float = 0.05) -> Dict[str, Any]:
    """Compound price growth (with optional rent) plus pessimistic/optimistic bands."""
    years = max(0, int(years or 0))
    base = gis.growth_series(current_value, cagr, years)
    low = gis.growth_series(current_value, cagr - 0.03, years)
    high = gis.growth_series(current_value, cagr + 0.03, years)
    series = []
    cumulative_rent = 0.0
    for row, lo, hi in zip(base, low, high):
        rent = 0.0
        if monthly_rent:
            rent = monthly_rent * 12 * (1 + rent_growth) ** row["offset"]
            cumulative_rent += rent
        series.append({"year": row["year"], "offset": row["offset"], "value": row["value"],
                       "low": lo["value"], "high": hi["value"],
                       "annual_rent": _round(rent), "cumulative_rent": _round(cumulative_rent),
                       "total_return": _round(row["value"] + cumulative_rent)})
    return {"current_value": _round(current_value), "cagr": cagr, "years": years,
            "final_value": series[-1]["value"] if series else _round(current_value),
            "total_gain": _round((series[-1]["value"] - current_value) if series else 0.0),
            "cumulative_rent": series[-1]["cumulative_rent"] if series else 0.0,
            "series": series}


# Statutory transfer-cost rates. ILLUSTRATIVE defaults only - the tool is meant to
# be configured with the current district rates for each province.
TRANSFER_RATES: Dict[str, Dict[str, float]] = {
    "punjab":     {"stamp_duty_pct": 3.0, "cvt_pct": 1.0, "registration_pct": 1.0,
                   "mutation_pct": 0.5, "withholding_filer_pct": 1.0, "withholding_nonfiler_pct": 2.0},
    "sindh":      {"stamp_duty_pct": 3.0, "cvt_pct": 1.0, "registration_pct": 1.0,
                   "mutation_pct": 0.5, "withholding_filer_pct": 1.0, "withholding_nonfiler_pct": 2.0},
    "kpk":        {"stamp_duty_pct": 3.0, "cvt_pct": 1.0, "registration_pct": 1.0,
                   "mutation_pct": 0.5, "withholding_filer_pct": 1.0, "withholding_nonfiler_pct": 2.0},
    "islamabad":  {"stamp_duty_pct": 3.0, "cvt_pct": 1.0, "registration_pct": 1.0,
                   "mutation_pct": 0.5, "withholding_filer_pct": 1.0, "withholding_nonfiler_pct": 2.0},
    "balochistan": {"stamp_duty_pct": 3.0, "cvt_pct": 1.0, "registration_pct": 1.0,
                    "mutation_pct": 0.5, "withholding_filer_pct": 1.0, "withholding_nonfiler_pct": 2.0},
}


def transfer_costs(price: float, province: str = "punjab", filer: bool = True,
                   rate_overrides: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """Stamp duty + CVT + registration + mutation + withholding for a property transfer."""
    price = float(price or 0.0)
    if price <= 0:
        return {"error": "price must be greater than zero"}
    rates = dict(TRANSFER_RATES.get((province or "punjab").lower(), TRANSFER_RATES["punjab"]))
    if rate_overrides:
        rates.update({k: float(v) for k, v in rate_overrides.items()})
    withholding = rates.get("withholding_filer_pct" if filer else "withholding_nonfiler_pct", 0.0)
    lines = [
        {"component": "Stamp duty", "rate_pct": rates.get("stamp_duty_pct", 0.0),
         "amount": _round(price * rates.get("stamp_duty_pct", 0.0) / 100.0)},
        {"component": "Capital value tax (CVT)", "rate_pct": rates.get("cvt_pct", 0.0),
         "amount": _round(price * rates.get("cvt_pct", 0.0) / 100.0)},
        {"component": "Registration fee", "rate_pct": rates.get("registration_pct", 0.0),
         "amount": _round(price * rates.get("registration_pct", 0.0) / 100.0)},
        {"component": "Mutation fee", "rate_pct": rates.get("mutation_pct", 0.0),
         "amount": _round(price * rates.get("mutation_pct", 0.0) / 100.0)},
        {"component": "Advance tax / withholding", "rate_pct": withholding,
         "amount": _round(price * withholding / 100.0)},
    ]
    total = sum(l["amount"] for l in lines)
    return {"price": _round(price), "province": province, "filer": filer,
            "lines": lines, "total_transfer_cost": _round(total),
            "total_pct": _round(total / price * 100, 3),
            "effective_price": _round(price + total),
            "assumptions": rates,
            "note": "Illustrative statutory rates - override with current district rates."}


def agent_commission(price: float, rate: Optional[float] = None, include_vat: bool = True) -> Dict[str, Any]:
    """Agent commission on a sale (with optional output VAT)."""
    price = float(price or 0.0)
    rate = TOOLS_CONFIG["agent_commission_rate"] if rate is None else float(rate)
    commission = price * rate
    vat = commission * TOOLS_CONFIG["vat_rate"] if include_vat else 0.0
    return {"price": _round(price), "rate": rate, "commission": _round(commission),
            "vat_rate": TOOLS_CONFIG["vat_rate"] if include_vat else 0.0, "vat": _round(vat),
            "total_payable": _round(commission + vat),
            "net_after_vat": _round(commission)}


# Illustrative capital-gains schedule for immovable property (FBR-style bands).
CGT_BANDS: Dict[str, List[Dict[str, Any]]] = {
    "filer": [{"max_holding_years": 1.0, "rate": 0.15}, {"max_holding_years": 2.0, "rate": 0.10},
              {"max_holding_years": 3.0, "rate": 0.075}, {"max_holding_years": None, "rate": 0.05}],
    "non_filer": [{"max_holding_years": 1.0, "rate": 0.20}, {"max_holding_years": 2.0, "rate": 0.15},
                  {"max_holding_years": 3.0, "rate": 0.125}, {"max_holding_years": None, "rate": 0.10}],
}


def capital_gains_tax(gain: float, holding_years: float, filer: bool = True) -> Dict[str, Any]:
    """Capital-gains tax on a property disposal, by holding period and filer status."""
    band_key = "filer" if filer else "non_filer"
    bands = CGT_BANDS[band_key]
    chosen = bands[-1]
    for b in bands:
        if b["max_holding_years"] is not None and holding_years <= b["max_holding_years"]:
            chosen = b
            break
    gain = float(gain or 0.0)
    tax = max(0.0, gain) * chosen["rate"]
    return {"gain": _round(gain), "holding_years": holding_years, "filer": filer,
            "rate_pct": _round(chosen["rate"] * 100, 3), "tax": _round(tax),
            "net_gain": _round(gain - tax), "bands": bands,
            "note": "Illustrative FBR schedule - confirm the current Finance Act rates."}


def joint_investment(partners: List[Dict[str, Any]], total_profit: float,
                     months: float = 12.0) -> Dict[str, Any]:
    """Split a profit between partners pro-rata to capital and show each partner's ROI."""
    capital = [float(p.get("capital") or 0.0) for p in (partners or [])]
    total_capital = sum(capital)
    if total_capital <= 0:
        return {"error": "Total partner capital must be greater than zero"}
    rows = []
    for p, c in zip(partners, capital):
        share = c / total_capital
        profit = float(total_profit or 0.0) * share
        roi = (profit / c) if c else 0.0
        annualised = ((1 + roi) ** (12.0 / months) - 1) if (c and months and roi > -1) else None
        rows.append({"partner": p.get("name") or f"partner_{len(rows) + 1}",
                     "capital": _round(c), "share_pct": _round(share * 100, 3),
                     "profit": _round(profit), "roi_pct": _round(roi * 100, 3),
                     "annualised_roi_pct": _round(annualised * 100, 3) if annualised is not None else None})
    return {"total_capital": _round(total_capital), "total_profit": _round(total_profit),
            "months": months, "partners": rows}


def construction_cost(covered_area: float, floors: int = 1, building_type: str = "house",
                      quality_tier: str = "standard", system: str = "rcc_frame",
                      city: Optional[str] = None, plot_area: Optional[float] = None,
                      escalation_years: float = 0.0) -> Dict[str, Any]:
    """Construction-cost estimate (reuses the construction wing's engine)."""
    return construction.estimate_construction(
        covered_area, floors=floors, building_type=building_type, quality_tier=quality_tier,
        system=system, city=city, plot_area=plot_area, escalation_years=escalation_years)


def material_quantities(covered_area: float, quality_tier: str = "standard",
                        building_type: str = "house") -> Dict[str, Any]:
    """Approximate material take-off (reuses the construction wing)."""
    return construction.material_takeoff(covered_area, quality_tier, building_type)


def build_timeline(covered_area: float, floors: int = 1, building_type: str = "house",
                   system: str = "rcc_frame") -> Dict[str, Any]:
    """Phase-weighted construction timeline (reuses the construction wing)."""
    return construction.timeline_estimate(covered_area, floors, building_type, system)


def rent_vs_buy(price: float, monthly_rent: float, down_payment_pct: float = 0.20,
                annual_rate: Optional[float] = None, years: Optional[int] = None,
                cagr: float = 0.08, rent_growth: float = 0.05, hold_years: int = 10) -> Dict[str, Any]:
    """Compare buying (with a mortgage) against renting and investing the difference."""
    price = float(price or 0.0)
    hold = max(1, int(hold_years or 1))
    down = price * float(down_payment_pct or 0.0)
    mort = mortgage_calculator(price, down, annual_rate, years)
    if "error" in mort:
        return mort
    buy_value = price * (1 + cagr) ** hold
    buy_equity = buy_value - max(0.0, mort["loan_amount"] - mort["periodic_payment"] * 12 * hold * 0.4)
    rent_paid = sum(monthly_rent * 12 * (1 + rent_growth) ** y for y in range(hold))
    return {"price": _round(price), "hold_years": hold, "annual_rate": mort["annual_rate"],
            "monthly_payment": mort["monthly_payment"], "down_payment": _round(down),
            "projected_value": _round(buy_value), "total_rent_paid": _round(rent_paid),
            "mortgage_total_interest": mort["total_interest"],
            "message": ("Buying builds equity while rent is unrecoverable, but ties up capital "
                        "and adds interest and transaction costs - compare against an "
                        "investment yielding the same capital."),
            "assumptions": {"down_payment_pct": down_payment_pct, "cagr": cagr,
                            "rent_growth": rent_growth}}


def calculator_catalog() -> Dict[str, Any]:
    """The calculators exposed by the wing, with their inputs and where they live."""
    rows = [
        {"key": "mortgage", "name": "Mortgage & home-financing calculator",
         "inputs": ["price", "down_payment", "annual_rate", "years"], "engine": "accounting.mortgage_schedule"},
        {"key": "installment", "name": "Monthly installment & down-payment calculator",
         "inputs": ["price", "down_payment", "months", "annual_markup"], "engine": "tools.installment_plan"},
        {"key": "rental_yield", "name": "Rental yield & ROI calculator",
         "inputs": ["price", "monthly_rent", "annual_costs", "vacancy_rate"], "engine": "tools.rental_yield"},
        {"key": "appreciation", "name": "Property appreciation & investment growth",
         "inputs": ["current_value", "cagr", "years", "monthly_rent"], "engine": "gis.growth_series"},
        {"key": "area", "name": "Price per sqft / marla / kanal & area converter",
         "inputs": ["value", "from_unit", "to_unit", "marla_sqft"], "engine": "tools.convert_area"},
        {"key": "plot_dimensions", "name": "Plot size & dimension calculator",
         "inputs": ["area", "from_unit", "ratio"], "engine": "tools.plot_dimensions"},
        {"key": "construction", "name": "Construction cost estimator",
         "inputs": ["covered_area", "floors", "building_type", "quality_tier", "city"], "engine": "construction.estimate_construction"},
        {"key": "transfer", "name": "Transfer, stamp duty & registration estimator",
         "inputs": ["price", "province", "filer"], "engine": "tools.transfer_costs"},
        {"key": "commission", "name": "Agent commission estimator",
         "inputs": ["price", "rate", "include_vat"], "engine": "tools.agent_commission"},
        {"key": "cgt", "name": "Capital-gains tax estimator",
         "inputs": ["gain", "holding_years", "filer"], "engine": "tools.capital_gains_tax"},
        {"key": "joint_investment", "name": "Joint investment & profit-sharing calculator",
         "inputs": ["partners", "total_profit", "months"], "engine": "tools.joint_investment"},
        {"key": "rent_vs_buy", "name": "Rent vs buy comparison",
         "inputs": ["price", "monthly_rent", "down_payment_pct", "hold_years"], "engine": "tools.rent_vs_buy"},
    ]
    return {"count": len(rows), "categories": ["calculators"], "calculators": rows}


def price_per_unit(price: float, area: float, from_unit: str = "sqft",
                   marla_sqft: float = 272.25) -> Dict[str, Any]:
    """Price per sqft / sqyd / sqm / marla for a listing."""
    try:
        sqft = float(area) * _sqft_per(from_unit, marla_sqft)
    except ValueError as exc:
        return {"error": str(exc), "units": AREA_UNITS}
    if sqft <= 0:
        return {"error": "area must be greater than zero"}
    price = float(price or 0.0)
    return {"price": _round(price), "area": _round(area, 4), "from_unit": from_unit,
            "area_sqft": _round(sqft),
            "price_per_sqft": _round(price / sqft),
            "price_per_sqyd": _round(price / (sqft / 9.0)),
            "price_per_sqm": _round(price / (sqft / 10.7639104167)),
            "price_per_marla": _round(price / (sqft / float(marla_sqft)))}


# ============================================================
# SAVED TOOL PROJECTS  (personalised tools)
# ============================================================


class SavedToolProject(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("proj_"))
    name: str = ""
    tool: str = ""
    inputs: Dict[str, Any] = Field(default_factory=dict)
    outputs: Dict[str, Any] = Field(default_factory=dict)
    notes: Optional[str] = None
    created_at: str = Field(default_factory=_now)


projects_db: List[SavedToolProject] = []


def save_project(name: str, tool: str, inputs: Optional[Dict[str, Any]] = None,
                 outputs: Optional[Dict[str, Any]] = None, notes: Optional[str] = None) -> SavedToolProject:
    rec = SavedToolProject(name=name, tool=tool, inputs=inputs or {}, outputs=outputs or {}, notes=notes)
    projects_db.append(rec)
    return rec


def list_projects(tool: Optional[str] = None) -> List[SavedToolProject]:
    rows = [p for p in projects_db if not tool or p.tool == tool]
    return sorted(rows, key=lambda p: p.created_at, reverse=True)


def find_project(project_id: str) -> Optional[SavedToolProject]:
    return next((p for p in projects_db if p.id == project_id), None)


def delete_project(project_id: str) -> bool:
    rec = find_project(project_id)
    if not rec:
        return False
    projects_db.remove(rec)
    return True


# ============================================================
# GIS / GEOREFERENCING / MAP MEASUREMENT
# ============================================================


def crs_catalog() -> Dict[str, Any]:
    """Common coordinate reference systems, with a note on which to use for area."""
    systems = [
        {"epsg": 4326, "name": "WGS 84 (geographic)", "units": "degrees",
         "use": "storage, GPS, GeoJSON/KML interchange",
         "note": "Do NOT compute area/perimeter in degrees - reproject first."},
        {"epsg": 3857, "name": "Web Mercator (Pseudo-Mercator)", "units": "metres",
         "use": "web slippy maps (Leaflet/MapLibre tiles)",
         "note": "Conformal, not equal-area - distances/areas distort away from the equator."},
        {"epsg": 32641, "name": "WGS 84 / UTM zone 41N", "units": "metres",
         "use": "Balochistan & western Sindh (60-66 E)", "note": "Metric, accurate local measurement."},
        {"epsg": 32642, "name": "WGS 84 / UTM zone 42N", "units": "metres",
         "use": "Punjab plains, KP (66-72 E), incl. Lahore/Islamabad", "note": "Metric, accurate local measurement."},
        {"epsg": 32643, "name": "WGS 84 / UTM zone 43N", "units": "metres",
         "use": "eastern Punjab, AJK (72-78 E)", "note": "Metric, accurate local measurement."},
    ]
    return {"count": len(systems), "systems": systems,
            "guidance": "Store as EPSG:4326; measure in the UTM zone for the area; render on 3857 tiles."}


def _pairs(coords: Any) -> List[List[float]]:
    """Normalise a coordinate list to [[lat, lon], ...] floats."""
    out: List[List[float]] = []
    for pair in coords or []:
        if isinstance(pair, dict):
            lat = pair.get("lat", pair.get("latitude"))
            lon = pair.get("lon", pair.get("lng", pair.get("longitude")))
        elif len(pair) >= 2:
            lat, lon = pair[0], pair[1]
        else:
            continue
        if lat is None or lon is None:
            continue
        out.append([float(lat), float(lon)])
    return out


def map_measure(coords: List[Any], marla_sqft: float = 272.25) -> Dict[str, Any]:
    """Distance, perimeter, area, centroid and bounding box for a set of points.

    ``coords`` is ``[[lat, lon], ...]``. Consecutive points are treated as a path;
    the ring is closed for perimeter and area.
    """
    pts = _pairs(coords)
    if len(pts) < 2:
        return {"error": "Provide at least two [lat, lon] points"}
    segments = []
    path_m = 0.0
    for a, b in zip(pts, pts[1:]):
        d = gis.haversine_m(a[0], a[1], b[0], b[1])
        path_m += d
        segments.append({"from": a, "to": b, "distance_m": _round(d),
                         "bearing_deg": gis.bearing_deg(a[0], a[1], b[0], b[1])})
    ring = gis.coords_from_latlon_list(pts)
    perimeter = path_m + gis.haversine_m(pts[-1][0], pts[-1][1], pts[0][0], pts[0][1])
    area_sqm = gis.polygon_area_sqm(ring)
    area_sqft = area_sqm * 10.7639104167
    centroid = gis.polygon_centroid(ring)
    return {
        "points": pts, "segments": segments,
        "path_length_m": _round(path_m), "path_length_km": _round(path_m / 1000.0, 3),
        "perimeter_m": _round(perimeter),
        "area_sqm": _round(area_sqm), "area_sqft": _round(area_sqft),
        "area_sqyd": _round(area_sqft / 9.0), "area_marla": _round(area_sqft / float(marla_sqft)),
        "area_kanal": _round(area_sqft / (float(marla_sqft) * 20.0)),
        "area_acre": _round(area_sqft / 43560.0),
        "centroid": {"lat": _round(centroid[0], 6), "lon": _round(centroid[1], 6)},
        "bbox": gis.bbox_of_coords(ring),
    }


def polygon_area_tool(coords: List[Any], unit: str = "sqft", marla_sqft: float = 272.25) -> Dict[str, Any]:
    """Area of a polygon from its coordinates, in the requested unit."""
    ring = gis.coords_from_latlon_list(_pairs(coords))
    if len(ring) < 3:
        return {"error": "Provide at least three [lat, lon] points"}
    sqft = gis.polygon_area_sqm(ring) * 10.7639104167
    return {"unit": unit, "sqft": _round(sqft),
            "all_units": {u: _round(sqft / _sqft_per(u, marla_sqft), 4) for u in AREA_UNITS},
            "value": _round(sqft / _sqft_per(unit, marla_sqft), 4),
            "centroid": {"lat": _round(gis.polygon_centroid(ring)[0], 6),
                         "lon": _round(gis.polygon_centroid(ring)[1], 6)}}


def _solve3(a: List[List[float]], b: List[float]) -> Optional[List[float]]:
    """Solve a 3x3 linear system by Gaussian elimination with partial pivoting."""
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    n = 3
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[pivot][col]) < 1e-12:
            return None
        m[col], m[pivot] = m[pivot], m[col]
        for r in range(n):
            if r == col:
                continue
            factor = m[r][col] / m[col][col]
            for c in range(col, n + 1):
                m[r][c] -= factor * m[col][c]
    return [m[i][n] / m[i][i] for i in range(n)]


def georeference(control_points: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Fit an image(px) -> WGS84 transform from control points.

    Each control point is ``{"image": [x, y], "geo": [lat, lon]}``. With three or
    more points an affine transform is least-squares fitted; with two a conformal
    (scale + rotation + translation) similarity is used; with one, a translation.
    Returns the matrix, per-point residuals and the inverse for drawing.
    """
    pts = []
    for cp in control_points or []:
        img = cp.get("image") or cp.get("px")
        geo = cp.get("geo") or cp.get("latlon")
        if not img or not geo or len(img) < 2 or len(geo) < 2:
            continue
        pts.append((float(img[0]), float(img[1]), float(geo[1]), float(geo[0])))  # x, y, lon, lat
    if not pts:
        return {"error": "Provide control points as {image:[x,y], geo:[lat,lon]}"}

    if len(pts) >= 3:
        s11 = s12 = s22 = 0.0
        t_lon = [0.0, 0.0, 0.0]
        t_lat = [0.0, 0.0, 0.0]
        for x, y, lon, lat in pts:
            s11 += x * x
            s12 += x * y
            s22 += y * y
            t_lon[0] += x * lon
            t_lon[1] += y * lon
            t_lon[2] += lon
            t_lat[0] += x * lat
            t_lat[1] += y * lat
            t_lat[2] += lat
        n = len(pts)
        A = [[s11, s12, sum(p[0] for p in pts)],
             [s12, s22, sum(p[1] for p in pts)],
             [sum(p[0] for p in pts), sum(p[1] for p in pts), float(n)]]
        clon = _solve3(A, t_lon)
        clat = _solve3(A, t_lat)
        if not clon or not clat:
            return {"error": "Control points are degenerate (collinear)"}
        a, b, c = clon
        d, e, f = clat
        model = "affine"
    elif len(pts) == 2:
        (x1, y1, lon1, lat1), (x2, y2, lon2, lat2) = pts
        dx, dy = x2 - x1, y2 - y1
        dlon, dlat = lon2 - lon1, lat2 - lat1
        denom = dx * dx + dy * dy
        if denom == 0:
            return {"error": "The two control points share the same image pixel"}
        a = (dlon * dx + dlat * dy) / denom
        b = (dlat * dx - dlon * dy) / denom
        c = lon1 - a * x1 + b * y1
        f = lat1 - b * x1 - a * y1
        d, e = b, a
        model = "similarity"
    else:
        x1, y1, lon1, lat1 = pts[0]
        a, b, d, e = 1.0, 0.0, 0.0, 1.0
        c = lon1 - x1
        f = lat1 - y1
        model = "translation"

    def predict(x: float, y: float) -> Tuple[float, float]:
        return (a * x + b * y + c, d * x + e * y + f)

    residuals = []
    sq = 0.0
    for x, y, lon, lat in pts:
        plon, plat = predict(x, y)
        err = gis.haversine_m(lat, lon, plat, plon)
        sq += err * err
        residuals.append({"image": [x, y], "geo": [lat, lon],
                          "predicted": [_round(plat, 6), _round(plon, 6)], "error_m": _round(err)})
    rmse = math.sqrt(sq / len(pts)) if pts else 0.0

    det = a * e - b * d
    inverse = None
    if abs(det) > 1e-15:
        inverse = {"a": e / det, "b": -b / det, "c": (b * f - e * c) / det,
                   "d": -d / det, "e": a / det, "f": (d * c - a * f) / det}

    return {"model": model, "control_points": len(pts), "rmse_m": _round(rmse, 3),
            "matrix": {"a": a, "b": b, "c": c, "d": d, "e": e, "f": f},
            "inverse": inverse,
            "formula": "lon = a*x + b*y + c ; lat = d*x + e*y + f  (image pixels -> WGS84)",
            "residuals": residuals,
            "quality": "good" if rmse <= 5 else ("fair" if rmse <= 25 else "poor"),
            "note": "3+ well-spread control points give the most reliable fit."}


def transform_point(matrix: Dict[str, float], x: float, y: float, to_geo: bool = True) -> Dict[str, Any]:
    """Apply a georeference matrix forward (px->geo) or inverse (geo->px)."""
    if not matrix:
        return {"error": "Provide a matrix {a,b,c,d,e,f}"}
    a, b, c = matrix.get("a", 1.0), matrix.get("b", 0.0), matrix.get("c", 0.0)
    d, e, f = matrix.get("d", 0.0), matrix.get("e", 1.0), matrix.get("f", 0.0)
    out1 = a * float(x) + b * float(y) + c
    out2 = d * float(x) + e * float(y) + f
    if to_geo:
        return {"lat": _round(out2, 7), "lon": _round(out1, 7)}
    return {"x": _round(out1, 3), "y": _round(out2, 3)}


def aerial_compare(scenes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compare dated aerial/satellite scenes: acquisition order, resolution, change."""
    rows = []
    for s in scenes or []:
        rows.append({"date": s.get("date"), "source": s.get("source"),
                     "resolution_m": s.get("resolution_m"),
                     "cloud_cover_pct": s.get("cloud_cover_pct"),
                     "url": s.get("url"), "license": s.get("license")})
    dated = sorted([r for r in rows if r.get("date")], key=lambda r: str(r["date"]))
    out: Dict[str, Any] = {"count": len(rows), "scenes": dated}
    if len(dated) >= 2:
        out["earliest"] = dated[0]
        out["latest"] = dated[-1]
        out["best_resolution_m"] = min((r["resolution_m"] for r in dated
                                        if r.get("resolution_m")), default=None)
    if len(dated) >= 2 and any(s.get("area_sqft") for s in scenes):
        a0 = next((s.get("area_sqft") for s in scenes if s.get("date") == dated[0]["date"]), None)
        a1 = next((s.get("area_sqft") for s in scenes if s.get("date") == dated[-1]["date"]), None)
        if a0 and a1:
            out["area_change_sqft"] = _round(a1 - a0)
    out["note"] = ("Satellite/aerial imagery cannot by itself establish legal boundaries or "
                   "ownership; display acquisition dates and resolution, and respect licensing.")
    return out


def export_geodata(features: List[Dict[str, Any]], fmt: str = "geojson",
                   name: str = "export") -> Dict[str, Any]:
    """Export points/lines/polygons as GeoJSON or KML.

    Each feature is ``{"kind": "point"|"line"|"polygon", "coords": [[lat,lon],...],
    "name": ..., "properties": {...}}``.
    """
    gj_features = []
    for f in features or []:
        kind = (f.get("kind") or "polygon").lower()
        pts = _pairs(f.get("coords"))
        props = dict(f.get("properties") or {})
        if f.get("name"):
            props.setdefault("name", f["name"])
        if kind == "point":
            gj_features.append(gis.point_feature(pts[0][0], pts[0][1], props))
        elif kind == "line":
            gj_features.append(gis.line_feature(pts, props))
        else:
            gj_features.append(gis.polygon_feature(pts, props))
    collection = gis.feature_collection(gj_features)
    fmt = (fmt or "geojson").lower()
    if fmt in ("geojson", "json"):
        return {"format": "geojson", "features": len(gj_features),
                "geojson": collection, "text": json.dumps(collection)}
    if fmt in ("kml", "google_earth"):
        layer = gis.GeoLayer(name=name, entity_type="property", entity_id="export", geojson=collection)
        kml = gis.build_kml(name, [layer])
        return {"format": "kml", "features": len(gj_features), "kml": kml, "text": kml}
    return {"error": f"Unsupported format: {fmt}", "formats": ["geojson", "kml"]}


_COORD_RE = re.compile(r"<coordinates>\s*([^<]+?)\s*</coordinates>", re.I)


def import_geodata(text: str) -> Dict[str, Any]:
    """Parse GeoJSON or KML text into [[lat, lon], ...] coordinate lists."""
    text = (text or "").strip()
    if not text:
        return {"error": "Provide GeoJSON or KML text"}
    if text[0] in "[{":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            return {"error": f"Invalid GeoJSON: {exc}"}
        features = data.get("features") if data.get("type") == "FeatureCollection" else [data]
        out = []
        for feat in features or []:
            geom = (feat or {}).get("geometry") or {}
            coords = geom.get("coordinates")
            kind = geom.get("type", "").lower()
            pts = _geojson_coords_to_latlon(coords, kind)
            if pts:
                out.append({"kind": kind, "coords": pts,
                            "properties": (feat or {}).get("properties", {})})
        return {"format": "geojson", "features": out, "count": len(out)}
    rings = _COORD_RE.findall(text)
    out = []
    for ring in rings:
        pts = []
        for token in ring.split():
            parts = token.split(",")
            if len(parts) >= 2:
                try:
                    pts.append([float(parts[1]), float(parts[0])])  # lon,lat -> lat,lon
                except ValueError:
                    continue
        if pts:
            out.append({"kind": "polygon" if len(pts) > 2 else "line", "coords": pts})
    if not out:
        return {"error": "No GeoJSON or KML coordinates found"}
    return {"format": "kml", "features": out, "count": len(out)}


def _geojson_coords_to_latlon(coords: Any, kind: str) -> List[List[float]]:
    pts: List[List[float]] = []

    def walk(node: Any) -> None:
        if isinstance(node, (list, tuple)):
            if node and isinstance(node[0], (int, float)) and len(node) >= 2:
                pts.append([float(node[1]), float(node[0])])
            else:
                for child in node:
                    walk(child)

    walk(coords)
    return pts


def locate_nearby(origin: List[float], pois: List[Dict[str, Any]], radius_m: float = 2000.0,
                  category: Optional[str] = None, limit: int = 20) -> Dict[str, Any]:
    """Find POIs within ``radius_m`` of an origin ``[lat, lon]``, nearest first."""
    o = _pairs([origin])
    if not o:
        return {"error": "Provide an origin as [lat, lon]"}
    lat0, lon0 = o[0]
    rows = []
    for p in pois or []:
        plat = p.get("latitude", p.get("lat"))
        plon = p.get("longitude", p.get("lon", p.get("lng")))
        if plat is None or plon is None:
            continue
        if category and (p.get("category") or "").lower() != category.lower():
            continue
        d = gis.haversine_m(lat0, lon0, float(plat), float(plon))
        if d <= radius_m:
            rows.append({"name": p.get("name"), "category": p.get("category"),
                         "latitude": float(plat), "longitude": float(plon),
                         "distance_m": _round(d),
                         "bearing_deg": gis.bearing_deg(lat0, lon0, float(plat), float(plon))})
    rows.sort(key=lambda r: r["distance_m"])
    return {"origin": {"lat": lat0, "lon": lon0}, "radius_m": radius_m,
            "count": len(rows), "nearest": rows[:limit]}


# ============================================================
# PLOT & CONSTRUCTION STUDIO
# ============================================================


def plot_diagram_svg(length_ft: float, width_ft: float, label: str = "Plot",
                     marla_sqft: float = 272.25) -> Dict[str, Any]:
    """A printable SVG diagram of a rectangular plot with its dimensions and area."""
    length_ft = float(length_ft or 0.0)
    width_ft = float(width_ft or 0.0)
    if length_ft <= 0 or width_ft <= 0:
        return {"error": "length_ft and width_ft must be greater than zero"}
    max_dim = max(length_ft, width_ft)
    scale = 480.0 / max_dim
    w = width_ft * scale
    h = length_ft * scale
    pad = 60.0
    area_sqft = length_ft * width_ft
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w + 2 * pad:.0f}" '
        f'height="{h + 2 * pad:.0f}" viewBox="0 0 {w + 2 * pad:.0f} {h + 2 * pad:.0f}" '
        f'font-family="Segoe UI, system-ui, sans-serif">'
        f'<rect width="100%" height="100%" fill="#ffffff"/>'
        f'<rect x="{pad:.1f}" y="{pad:.1f}" width="{w:.1f}" height="{h:.1f}" '
        f'fill="#e0f2fe" stroke="#0369a1" stroke-width="2"/>'
        f'<text x="{pad + w / 2:.1f}" y="{pad - 14:.1f}" text-anchor="middle" font-size="14" '
        f'fill="#0f172a">{_esc(label)} — {width_ft:g} ft</text>'
        f'<text x="{pad - 10:.1f}" y="{pad + h / 2:.1f}" text-anchor="middle" font-size="14" '
        f'fill="#0f172a" transform="rotate(-90 {pad - 10:.1f} {pad + h / 2:.1f})">{length_ft:g} ft</text>'
        f'<text x="{pad + w / 2:.1f}" y="{pad + h + 26:.1f}" text-anchor="middle" font-size="13" '
        f'fill="#334155">{area_sqft:,.0f} sqft · {area_sqft / marla_sqft:,.2f} marla</text>'
        f'</svg>'
    )
    return {"svg": svg, "length_ft": length_ft, "width_ft": width_ft,
            "area_sqft": _round(area_sqft), "area_marla": _round(area_sqft / marla_sqft)}


def plot_studio(value: float, from_unit: str = "marla", ratio: float = 2.0,
                covered_area: Optional[float] = None, quality_tier: str = "standard",
                building_type: str = "house", marla_sqft: float = 272.25) -> Dict[str, Any]:
    """A one-shot plot brief: all-unit conversion, dimensions, diagram and (optional) build cost."""
    conv = convert_area_all(value, from_unit, marla_sqft)
    if "error" in conv:
        return conv
    dims = plot_dimensions(value, from_unit, ratio, marla_sqft)
    diagram = plot_diagram_svg(dims["length_ft"], dims["width_ft"],
                               label=f"{value:g} {from_unit} plot", marla_sqft=marla_sqft)
    out: Dict[str, Any] = {"conversion": conv["conversions"], "dimensions": dims,
                           "diagram_svg": diagram.get("svg"),
                           "marla_standards": dict(MARLA_STANDARDS)}
    if covered_area:
        out["construction"] = construction.estimate_construction(
            covered_area, building_type=building_type, quality_tier=quality_tier)
    return out


# ============================================================
# CAD / PLAN UTILITIES
# ============================================================

CAD_FORMATS: List[Dict[str, Any]] = [
    {"format": "DXF (ASCII)", "ext": [".dxf"], "preview": "native", "convert": "native",
     "layers": "yes", "note": "Text format - parsed and rendered here without extra software."},
    {"format": "DXF (binary)", "ext": [".dxf"], "preview": "guidance", "convert": "limit",
     "layers": "yes", "note": "Binary DXF needs a CAD library (ezdxf) to decode."},
    {"format": "DWG", "ext": [".dwg"], "preview": "guidance", "convert": "licensed",
     "layers": "yes", "note": "Proprietary; requires ODA/Teigha or a licensed service."},
    {"format": "DGN", "ext": [".dgn"], "preview": "guidance", "convert": "licensed",
     "layers": "yes", "note": "MicroStation format; needs a licensed converter."},
    {"format": "PDF/images", "ext": [".pdf", ".png", ".jpg"], "preview": "yes", "convert": "yes",
     "layers": "no", "note": "Raster/print preview only - editable CAD layers are not preserved."},
]


def cad_formats() -> Dict[str, Any]:
    """Supported drawing formats and what each can actually do."""
    return {"count": len(CAD_FORMATS), "formats": CAD_FORMATS,
            "note": CAD_FORMAT_NOTE}


CAD_FORMAT_NOTE = ("DWG and DGN are specialized proprietary formats. Full compatibility may "
                   "require licensed conversion software or a dedicated processing service. "
                   "PDF/image conversion alone will not preserve editable CAD layers.")


def cad_inspect(filename: str = "", head_base64: Optional[str] = None,
                size_bytes: int = 0) -> Dict[str, Any]:
    """Detect a drawing's format from its name and first bytes, and report capabilities."""
    head = b""
    if head_base64:
        try:
            head = base64.b64decode(head_base64)[:256]
        except (ValueError, TypeError):
            head = b""
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in (filename or "") else ""
    detected = None
    version = None
    if head[:4] == b"AC10":
        detected, version = "DWG", head[:6].decode("ascii", "replace")
    elif head.startswith(b"AutoCAD Binary DXF"):
        detected = "DXF (binary)"
    elif b"SECTION" in head or b"AutoCAD" in head or (head and head.lstrip()[:1] == b"0"):
        detected = "DXF (ASCII)"
        m = re.search(rb"AC10\d+", head)
        version = m.group(0).decode("ascii") if m else None
    elif head[:4] == b"%PDF":
        detected = "PDF"
    elif head[:3] == b"\xff\xd8\xff":
        detected = "JPEG"
    elif head[:8] == b"\x89PNG\r\n\x1a\n":
        detected = "PNG"
    if not detected:
        for f in CAD_FORMATS:
            if ext and ext in f["ext"]:
                detected = f["format"]
                break
    info = next((f for f in CAD_FORMATS if f["format"] == detected), None)
    return {"filename": filename, "size_bytes": size_bytes, "extension": ext,
            "detected_format": detected, "version": version,
            "capability": info,
            "native_preview": bool(info and info["preview"] == "native"),
            "note": CAD_FORMAT_NOTE}


def parse_dxf(text: str) -> Dict[str, Any]:
    """Parse the ENTITIES of an ASCII DXF into a small, renderable entity list.

    Supports LINE, LWPOLYLINE, POLYLINE/VERTEX, CIRCLE, ARC and TEXT/MTEXT.
    """
    lines = (text or "").splitlines()
    pairs: List[Tuple[str, str]] = []
    i = 0
    while i + 1 < len(lines):
        code = lines[i].strip()
        value = lines[i + 1].strip()
        pairs.append((code, value))
        i += 2
    entities: List[Dict[str, Any]] = []
    layers: Dict[str, int] = {}
    current: Optional[Dict[str, Any]] = None
    in_polyline = False

    def flush() -> None:
        nonlocal current
        if current and current.get("type"):
            entities.append(current)
        current = None

    for code, value in pairs:
        if code == "0":
            if value == "POLYLINE":
                flush()
                in_polyline = True
                current = {"type": "polyline", "points": []}
                continue
            if value == "VERTEX" and in_polyline:
                continue
            if value == "SEQEND":
                if in_polyline:
                    flush()
                    in_polyline = False
                continue
            flush()
            if value in ("LINE", "LWPOLYLINE", "CIRCLE", "ARC", "TEXT", "MTEXT"):
                kind = {"LWPOLYLINE": "polyline", "TEXT": "text", "MTEXT": "text"}.get(value, value.lower())
                current = {"type": kind, "points": []}
            continue
        if current is None:
            continue
        if code == "8":
            current["layer"] = value
            layers[value] = layers.get(value, 0) + 1
        elif code in ("10", "20"):
            try:
                num = float(value)
            except ValueError:
                continue
            if code == "10":
                current.setdefault("points", []).append([num, 0.0])
            else:
                pts = current.setdefault("points", [])
                if not pts:
                    pts.append([0.0, num])
                else:
                    pts[-1][1] = num
        elif code == "11":
            try:
                current.setdefault("points", []).append([float(value), 0.0])
            except ValueError:
                pass
        elif code == "21":
            pts = current.setdefault("points", [])
            if pts:
                pts[-1][1] = float(value)
        elif code == "40":
            try:
                current["radius"] = float(value)
            except ValueError:
                pass
        elif code in ("1", "50", "51"):
            current["text" if code == "1" else ("start_angle" if code == "50" else "end_angle")] = value
    flush()
    xs = [p[0] for e in entities for p in e.get("points", []) if len(p) >= 2]
    ys = [p[1] for e in entities for p in e.get("points", []) if len(p) >= 2]
    bbox = {"min_x": min(xs), "min_y": min(ys), "max_x": max(xs), "max_y": max(ys)} if xs and ys else None
    return {"entities": entities, "entity_count": len(entities),
            "by_type": {t: sum(1 for e in entities if e["type"] == t)
                        for t in sorted({e["type"] for e in entities})},
            "layers": layers, "bbox": bbox}


def entities_to_svg(entities: List[Dict[str, Any]], width: int = 800, height: int = 600,
                    stroke: str = "#0f172a") -> Dict[str, Any]:
    """Render a simple entity list to an SVG string (auto-fitted to the canvas)."""
    xs: List[float] = []
    ys: List[float] = []
    for e in entities or []:
        for p in e.get("points", []):
            if len(p) >= 2:
                xs.append(float(p[0]))
                ys.append(float(p[1]))
    if not xs or not ys:
        return {"error": "No drawable entities"}
    min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
    span_x = (max_x - min_x) or 1.0
    span_y = (max_y - min_y) or 1.0
    pad = 20.0
    scale = min((width - 2 * pad) / span_x, (height - 2 * pad) / span_y)

    def sx(x: float) -> float:
        return pad + (x - min_x) * scale

    def sy(y: float) -> float:
        return height - pad - (y - min_y) * scale

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
             f'viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="#ffffff"/>']
    for e in entities or []:
        t = e.get("type")
        pts = e.get("points", [])
        if t == "line" and len(pts) >= 2:
            parts.append(f'<line x1="{sx(pts[0][0]):.1f}" y1="{sy(pts[0][1]):.1f}" '
                         f'x2="{sx(pts[1][0]):.1f}" y2="{sy(pts[1][1]):.1f}" '
                         f'stroke="{stroke}" stroke-width="1.4"/>')
        elif t == "polyline" and len(pts) >= 2:
            poly = " ".join(f"{sx(p[0]):.1f},{sy(p[1]):.1f}" for p in pts)
            parts.append(f'<polyline points="{poly}" fill="none" stroke="{stroke}" stroke-width="1.4"/>')
        elif t in ("circle", "arc") and pts and e.get("radius"):
            r = float(e["radius"]) * scale
            parts.append(f'<circle cx="{sx(pts[0][0]):.1f}" cy="{sy(pts[0][1]):.1f}" r="{r:.1f}" '
                         f'fill="none" stroke="{stroke}" stroke-width="1.4"/>')
        elif t == "text" and pts and e.get("text"):
            parts.append(f'<text x="{sx(pts[0][0]):.1f}" y="{sy(pts[0][1]):.1f}" font-size="11" '
                         f'fill="{stroke}">{_esc(str(e["text"]))}</text>')
    parts.append("</svg>")
    return {"svg": "".join(parts), "entities": len(entities or []),
            "bbox": {"min_x": min_x, "min_y": min_y, "max_x": max_x, "max_y": max_y}}


def dxf_preview(text: str, width: int = 800, height: int = 600) -> Dict[str, Any]:
    """Parse an ASCII DXF and render it to SVG in one call."""
    parsed = parse_dxf(text)
    if not parsed.get("entities"):
        return {**parsed, "error": "No renderable entities found in the DXF"}
    svg = entities_to_svg(parsed["entities"], width, height)
    return {"entity_count": parsed["entity_count"], "by_type": parsed["by_type"],
            "layers": parsed["layers"], "bbox": parsed["bbox"], "svg": svg.get("svg")}


def compare_revisions(a_entities: List[Dict[str, Any]], b_entities: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compare two revisions of a plan: counts, extents and added/removed items."""

    def key(e: Dict[str, Any]) -> str:
        pts = tuple(tuple(round(float(v), 3) for v in p[:2]) for p in e.get("points", []) if len(p) >= 2)
        return f"{e.get('type')}|{e.get('layer')}|{pts}"

    ka = {key(e) for e in a_entities or []}
    kb = {key(e) for e in b_entities or []}
    added = sorted(kb - ka)
    removed = sorted(ka - kb)

    def extent(entities: List[Dict[str, Any]]) -> Optional[Dict[str, float]]:
        xs = [float(p[0]) for e in entities or [] for p in e.get("points", []) if len(p) >= 2]
        ys = [float(p[1]) for e in entities or [] for p in e.get("points", []) if len(p) >= 2]
        if not xs or not ys:
            return None
        return {"min_x": min(xs), "min_y": min(ys), "max_x": max(xs), "max_y": max(ys)}

    return {"revision_a": {"entities": len(a_entities or []), "bbox": extent(a_entities)},
            "revision_b": {"entities": len(b_entities or []), "bbox": extent(b_entities)},
            "added": len(added), "removed": len(removed),
            "unchanged": len(ka & kb), "changed": bool(added or removed),
            "added_keys": added[:50], "removed_keys": removed[:50]}


def printable_layout_sheet(title: str, plot_length_ft: float, plot_width_ft: float,
                           orientation: str = "portrait") -> Dict[str, Any]:
    """A printable plot-layout sheet (SVG) with a title block and a scale bar."""
    plot_length_ft = float(plot_length_ft or 0.0)
    plot_width_ft = float(plot_width_ft or 0.0)
    if plot_length_ft <= 0 or plot_width_ft <= 0:
        return {"error": "plot dimensions must be greater than zero"}
    if orientation == "landscape":
        w, h = 1123, 794
    else:
        w, h = 794, 1123
    margin = 48.0
    area_w = w - 2 * margin
    area_h = h - 2 * margin - 90
    scale = min(area_w / plot_width_ft, area_h / plot_length_ft)
    pw = plot_width_ft * scale
    ph = plot_length_ft * scale
    x = margin + (area_w - pw) / 2
    y = margin + 40
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'font-family="Segoe UI, system-ui, sans-serif">'
        f'<rect width="100%" height="100%" fill="#ffffff" stroke="#0f172a"/>'
        f'<text x="{margin}" y="{margin}" font-size="20" font-weight="700" fill="#0f172a">{_esc(title)}</text>'
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{pw:.1f}" height="{ph:.1f}" fill="#f1f5f9" '
        f'stroke="#0369a1" stroke-width="2"/>'
        f'<text x="{x + pw / 2:.1f}" y="{y + ph / 2:.1f}" text-anchor="middle" font-size="12" fill="#334155">'
        f'{plot_width_ft:g} ft × {plot_length_ft:g} ft</text>'
        f'<line x1="{margin}" y1="{h - margin}" x2="{margin + 100}" y2="{h - margin}" stroke="#0f172a"/>'
        f'<text x="{margin}" y="{h - margin - 6}" font-size="11" fill="#334155">scale bar</text>'
        f'</svg>'
    )
    return {"svg": svg, "orientation": orientation,
            "area_sqft": _round(plot_length_ft * plot_width_ft),
            "sheet": f"{w}x{h}"}


def _esc(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# ============================================================
# PHOTO LOCATION & GEOTAGGING  (real, dependency-free EXIF GPS)
# ============================================================

_TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8}


def _unb64(value: str) -> bytes:
    if not value:
        return b""
    if value.startswith("data:") and "," in value:
        value = value.split(",", 1)[1]
    try:
        return base64.b64decode(value)
    except (ValueError, TypeError):
        return b""


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _find_exif_tiff(data: bytes) -> Optional[bytes]:
    if data[:2] != b"\xff\xd8":
        return None
    i = 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            return None
        marker = data[i + 1]
        if marker == 0xD8 or marker == 0x01 or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        if marker == 0xDA:
            return None
        seg_len = int.from_bytes(data[i + 2:i + 4], "big")
        if marker == 0xE1 and data[i + 4:i + 10] == b"Exif\x00\x00":
            return data[i + 10:i + 2 + seg_len]
        i += 2 + seg_len
    return None


def _ifd_entries(tiff: bytes, offset: int, endian: str) -> Dict[int, Dict[str, Any]]:
    if offset + 2 > len(tiff):
        return {}
    count = struct.unpack(endian + "H", tiff[offset:offset + 2])[0]
    entries: Dict[int, Dict[str, Any]] = {}
    for k in range(count):
        base = offset + 2 + k * 12
        if base + 12 > len(tiff):
            break
        tag, typ, cnt = struct.unpack(endian + "HHI", tiff[base:base + 8])
        size = _TYPE_SIZE.get(typ, 1) * cnt
        inline = tiff[base + 8:base + 12]
        if size <= 4:
            raw = inline[:size]
        else:
            voff = struct.unpack(endian + "I", inline)[0]
            raw = tiff[voff:voff + size]
        entries[tag] = {"type": typ, "count": cnt, "raw": raw}
    return entries


def _rational(entry: Dict[str, Any], endian: str, index: int = 0) -> Optional[float]:
    raw = entry.get("raw") or b""
    off = index * 8
    if off + 8 > len(raw):
        return None
    num, den = struct.unpack(endian + "II", raw[off:off + 8])
    return (num / den) if den else 0.0


def read_photo_gps(image_base64: str) -> Dict[str, Any]:
    """Read GPS coordinates (and altitude/time) embedded in a JPEG's EXIF."""
    data = _unb64(image_base64)
    if not data:
        return {"error": "Provide a JPEG as base64"}
    tiff = _find_exif_tiff(data)
    if not tiff:
        return {"has_gps": False, "message": "No EXIF GPS metadata found in this image"}
    endian = "<" if tiff[:2] == b"II" else ">"
    if len(tiff) < 8 or struct.unpack(endian + "H", tiff[2:4])[0] != 42:
        return {"has_gps": False, "message": "Malformed EXIF block"}
    ifd0_off = struct.unpack(endian + "I", tiff[4:8])[0]
    ifd0 = _ifd_entries(tiff, ifd0_off, endian)
    gps_ptr = ifd0.get(0x8825)
    if not gps_ptr:
        return {"has_gps": False, "message": "EXIF present but no GPS IFD"}
    try:
        gps_off = struct.unpack(endian + "I", gps_ptr["raw"][:4])[0]
    except struct.error:
        return {"has_gps": False, "message": "Malformed GPS IFD pointer"}
    gps = _ifd_entries(tiff, gps_off, endian)

    def dms(tag: int) -> Optional[float]:
        e = gps.get(tag)
        if not e:
            return None
        parts = [_rational(e, endian, i) for i in range(3)]
        if any(p is None for p in parts):
            return None
        return parts[0] + parts[1] / 60.0 + parts[2] / 3600.0

    def ref(tag: int, default: str) -> str:
        e = gps.get(tag)
        if not e:
            return default
        return (e["raw"] or default.encode())[:1].decode("ascii", "replace") or default

    lat, lon = dms(0x0002), dms(0x0004)
    if lat is None or lon is None:
        return {"has_gps": False, "message": "GPS IFD present but no coordinates"}
    if ref(0x0001, "N") == "S":
        lat = -lat
    if ref(0x0003, "E") == "W":
        lon = -lon
    alt = _rational(gps.get(0x0006), endian) if gps.get(0x0006) else None
    altitude = None
    if alt is not None:
        alt_ref = gps.get(0x0005)
        below = bool(alt_ref and (alt_ref["raw"] or b"\x00")[0])
        altitude = -alt if below else alt
    stamp = gps.get(0x0007)
    timestamp = None
    if stamp:
        h = _rational(stamp, endian, 0)
        m = _rational(stamp, endian, 1)
        s = _rational(stamp, endian, 2)
        if h is not None:
            timestamp = f"{int(h):02d}:{int(m or 0):02d}:{int(s or 0):02d} UTC"
    return {"has_gps": True, "latitude": _round(lat, 7), "longitude": _round(lon, 7),
            "altitude_m": _round(altitude, 2) if altitude is not None else None,
            "timestamp": timestamp}


def _dms_rationals(value: float) -> List[Tuple[int, int]]:
    value = abs(float(value))
    deg = int(value)
    minutes = int((value - deg) * 60)
    seconds = (value - deg - minutes / 60.0) * 3600.0
    return [(deg, 1), (minutes, 1), (int(round(seconds * 10000)), 10000)]


def _build_exif_app1(latitude: float, longitude: float, altitude: Optional[float],
                     dt: Optional[datetime]) -> bytes:
    endian = "<"
    lat_ref = b"N" if latitude >= 0 else b"S"
    lon_ref = b"E" if longitude >= 0 else b"W"

    def rb(pairs: List[Tuple[int, int]]) -> bytes:
        return b"".join(struct.pack(endian + "II", n, d) for n, d in pairs)

    entries: List[Dict[str, Any]] = [
        {"tag": 0x0000, "type": 1, "count": 4, "data": b"\x02\x03\x00\x00"},
        {"tag": 0x0001, "type": 2, "count": 2, "data": lat_ref + b"\x00"},
        {"tag": 0x0002, "type": 5, "count": 3, "data": rb(_dms_rationals(latitude))},
        {"tag": 0x0003, "type": 2, "count": 2, "data": lon_ref + b"\x00"},
        {"tag": 0x0004, "type": 5, "count": 3, "data": rb(_dms_rationals(longitude))},
    ]
    if altitude is not None:
        entries.append({"tag": 0x0005, "type": 1, "count": 1,
                        "data": b"\x00" if altitude >= 0 else b"\x01"})
        entries.append({"tag": 0x0006, "type": 5, "count": 1,
                        "data": rb([(int(round(abs(altitude) * 100)), 100)])})
    if dt is not None:
        entries.append({"tag": 0x0007, "type": 5, "count": 3,
                        "data": rb([(dt.hour, 1), (dt.minute, 1), (dt.second, 1)])})

    ifd_offset = 26  # TIFF header (8) + IFD0 (18)
    count = len(entries)
    data_cursor = ifd_offset + 2 + 12 * count + 4
    entry_bytes = b""
    pool = b""
    for e in entries:
        data = e["data"]
        if len(data) <= 4:
            value_field = data.ljust(4, b"\x00")
        else:
            value_field = struct.pack(endian + "I", data_cursor + len(pool))
            pool += data
            if len(pool) % 2:
                pool += b"\x00"
        entry_bytes += struct.pack(endian + "HHI", e["tag"], e["type"], e["count"]) + value_field
    gps_ifd = struct.pack(endian + "H", count) + entry_bytes + struct.pack(endian + "I", 0)
    ifd0 = (struct.pack(endian + "H", 1)
            + struct.pack(endian + "HHI", 0x8825, 4, 1)
            + struct.pack(endian + "I", ifd_offset)
            + struct.pack(endian + "I", 0))
    tiff = b"II" + struct.pack(endian + "HI", 42, 8) + ifd0 + gps_ifd + pool
    payload = b"Exif\x00\x00" + tiff
    return b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload


def _rewrite_jpeg_gps(data: bytes, app1: bytes) -> Optional[bytes]:
    if data[:2] != b"\xff\xd8":
        return None
    out = bytearray(b"\xff\xd8")
    i = 2
    if i + 4 <= len(data) and data[i:i + 2] == b"\xff\xe0":  # keep a leading JFIF APP0
        seg_len = int.from_bytes(data[i + 2:i + 4], "big")
        out += data[i:i + 2 + seg_len]
        i += 2 + seg_len
    out += app1
    while i + 1 < len(data) and data[i] == 0xFF and data[i + 1] != 0xDA:
        marker = data[i + 1]
        if marker == 0x01 or 0xD0 <= marker <= 0xD7:
            out += data[i:i + 2]
            i += 2
            continue
        if i + 4 > len(data):
            break
        seg_len = int.from_bytes(data[i + 2:i + 4], "big")
        if marker == 0xE1 and data[i + 4:i + 10] == b"Exif\x00\x00":
            i += 2 + seg_len  # drop the previous EXIF block
            continue
        out += data[i:i + 2 + seg_len]
        i += 2 + seg_len
    out += data[i:]
    return bytes(out)


def write_photo_gps(image_base64: str, latitude: float, longitude: float,
                    altitude: Optional[float] = None,
                    timestamp: Optional[str] = None) -> Dict[str, Any]:
    """Embed/replace GPS coordinates in a JPEG's EXIF, returning new base64 bytes."""
    data = _unb64(image_base64)
    if not data:
        return {"error": "Provide a JPEG as base64"}
    if not (-90 <= float(latitude) <= 90 and -180 <= float(longitude) <= 180):
        return {"error": "latitude must be within [-90, 90] and longitude within [-180, 180]"}
    dt = None
    if timestamp:
        try:
            dt = datetime.fromisoformat(timestamp)
        except ValueError:
            return {"error": "timestamp must be ISO-8601, e.g. 2026-05-01T10:30:00"}
    app1 = _build_exif_app1(float(latitude), float(longitude), altitude, dt)
    new_data = _rewrite_jpeg_gps(data, app1)
    if new_data is None:
        return {"error": "Not a valid JPEG (must start with FFD8)"}
    return {"written": True, "image_base64": _b64(new_data),
            "latitude": _round(latitude, 7), "longitude": _round(longitude, 7),
            "altitude_m": _round(altitude, 2) if altitude is not None else None,
            "bytes": len(new_data)}


def geo_privacy_check(latitude: float, longitude: float) -> Dict[str, Any]:
    """Advise on sharing precise residential coordinates."""
    lat, lon = _round(latitude, 7), _round(longitude, 7)
    fuzzed = {"latitude": _round(round(latitude, 3), 3), "longitude": _round(round(longitude, 3), 3)}
    return {"latitude": lat, "longitude": lon, "precision_m": _round(
        gis.haversine_m(lat, lon, lat + 0.0000001, lon + 0.0000001), 3),
        "recommendation": "Embedding precise residential coordinates is optional; warn before "
                          "sharing. Round to ~3 decimals (~110 m) for public listings.",
        "fuzzed": fuzzed,
        "note": "Make location embedding opt-in, especially for occupied homes."}


def photo_geotag_batch(photos: List[Dict[str, Any]], latitude: float, longitude: float,
                       altitude: Optional[float] = None) -> Dict[str, Any]:
    """Geotag several photos with the same coordinate (batch)."""
    results = []
    for p in photos or []:
        res = write_photo_gps(p.get("image_base64", ""), latitude, longitude,
                              altitude=p.get("altitude", altitude),
                              timestamp=p.get("timestamp"))
        res["name"] = p.get("name")
        results.append(res)
    return {"count": len(results), "latitude": _round(latitude, 7),
            "longitude": _round(longitude, 7),
            "tagged": sum(1 for r in results if r.get("written")), "results": results}


def photo_markers(photos: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build map markers (for ``gis.build_map_html``) from geotagged photos."""
    markers = []
    for p in photos or []:
        lat = p.get("latitude")
        lon = p.get("longitude")
        if lat is None or lon is None:
            continue
        markers.append({"lat": float(lat), "lon": float(lon),
                        "label": p.get("name") or p.get("label") or "photo",
                        "popup": p.get("timestamp") or "",
                        "group": p.get("group")})
    return {"count": len(markers), "markers": markers}


def photo_report(photos: List[Dict[str, Any]], title: str = "Site photo report",
                 lang: str = "en", theme: str = "auto") -> Dict[str, Any]:
    """A property photo report: markers, a summary table and an embeddable map."""
    markers = photo_markers(photos)["markers"]
    rows = []
    for p in photos or []:
        rows.append({"name": p.get("name"), "latitude": p.get("latitude"),
                     "longitude": p.get("longitude"), "timestamp": p.get("timestamp")})
    map_html = ""
    if markers:
        center = {
            "lat": sum(m["lat"] for m in markers) / len(markers),
            "lon": sum(m["lon"] for m in markers) / len(markers),
        }
        map_html = gis.build_map_html(title=title, center_lat=center["lat"], center_lon=center["lon"],
                                      zoom=15, markers=markers, lang=lang, theme=theme)
    return {"title": title, "count": len(rows), "photo_count": len(rows),
            "markers": markers, "rows": rows, "map_html": map_html}


# ============================================================
# DOCUMENT & FILE CONVERSION  (pure-Python PDF writer; guidance elsewhere)
# ============================================================


def _pdf_escape(text: str) -> str:
    return str(text).replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


PAGE_SIZES: Dict[str, Tuple[float, float]] = {"a4": (595, 842), "letter": (612, 792),
                                              "a3": (842, 1191)}


def _serialize_pdf(objects: List[Tuple[int, bytes]]) -> bytes:
    header = b"%PDF-1.4\n"
    body = b""
    offsets: Dict[int, int] = {}
    for oid, data in objects:
        offsets[oid] = len(header) + len(body)
        body += f"{oid} 0 obj\n".encode("ascii") + data + b"\nendobj\n"
    xref_off = len(header) + len(body)
    max_id = max(offsets) if offsets else 0
    xref = f"xref\n0 {max_id + 1}\n0000000000 65535 f \n"
    for i in range(1, max_id + 1):
        xref += f"{offsets.get(i, 0):010d} 00000 n \n"
    trailer = f"trailer\n<< /Size {max_id + 1} /Root 1 0 R >>\nstartxref\n{xref_off}\n%%EOF\n"
    return header + body + xref.encode("ascii") + trailer.encode("ascii")


def text_to_pdf(title: str, lines: List[str], page_size: str = "a4") -> Dict[str, Any]:
    """Create a simple text PDF (dependency-free)."""
    width, height = PAGE_SIZES.get((page_size or "a4").lower(), PAGE_SIZES["a4"])
    margin, font_size, leading = 50.0, 12.0, 16.0
    max_chars = max(20, int((width - 2 * margin) / (font_size * 0.5)))
    wrapped: List[str] = []
    for raw in [title] + list(lines or []):
        text = "" if raw is None else str(raw)
        if not text:
            wrapped.append("")
            continue
        while len(text) > max_chars:
            cut = text.rfind(" ", 0, max_chars)
            cut = cut if cut > 0 else max_chars
            wrapped.append(text[:cut])
            text = text[cut:].lstrip()
        wrapped.append(text)
    per_page = max(1, int((height - 2 * margin) / leading))
    pages = [wrapped[i:i + per_page] for i in range(0, len(wrapped), per_page)] or [[]]
    n = len(pages)
    font_id = 3 + n * 2
    objects: List[Tuple[int, bytes]] = []
    kids = " ".join(f"{3 + i * 2} 0 R" for i in range(n))
    objects.append((1, f"<< /Type /Catalog /Pages 2 0 R >>".encode("ascii")))
    objects.append((2, f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode("ascii")))
    for i, page_lines in enumerate(pages):
        page_id, content_id = 3 + i * 2, 4 + i * 2
        objects.append((page_id, (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width:g} {height:g}] "
                                  f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
                                  f"/Contents {content_id} 0 R >>").encode("ascii")))
        stream = ["BT", f"/F1 {font_size:g} Tf", f"{margin:g} {height - margin:g} Td", f"{leading:g} TL"]
        for ln in page_lines:
            stream.append(f"({_pdf_escape(ln)}) Tj T*")
        stream.append("ET")
        s = "\n".join(stream).encode("ascii", "replace")
        objects.append((content_id, b"<< /Length " + str(len(s)).encode() + b" >>\nstream\n" + s + b"\nendstream"))
    objects.append((font_id, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"))
    pdf = _serialize_pdf(objects)
    return {"pdf_base64": _b64(pdf), "pages": n, "bytes": len(pdf)}


def _jpeg_size(data: bytes) -> Optional[Tuple[int, int, int]]:
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            height = int.from_bytes(data[i + 5:i + 7], "big")
            width = int.from_bytes(data[i + 7:i + 9], "big")
            comps = data[i + 9]
            return width, height, comps
        if marker == 0xDA:
            return None
        seg_len = int.from_bytes(data[i + 2:i + 4], "big")
        i += 2 + seg_len
    return None


def images_to_pdf(images: List[Dict[str, Any]], page_size: str = "a4") -> Dict[str, Any]:
    """Combine JPEG images into a PDF (native DCTDecode, no re-encoding).

    Non-JPEG images need a decoder (Pillow) - they are reported back as skipped.
    """
    width_pt, height_pt = PAGE_SIZES.get((page_size or "a4").lower(), PAGE_SIZES["a4"])
    bounded = [img for img in (images or []) if img.get("image_base64")]
    pages_data: List[Tuple[Dict[str, Any], bytes]] = []
    skipped = []
    for img in bounded:
        data = _unb64(img.get("image_base64", ""))
        if not data.startswith(b"\xff\xd8"):
            skipped.append({"name": img.get("name"), "reason": "not a JPEG (decode with Pillow first)"})
            continue
        dims = _jpeg_size(data)
        if not dims:
            skipped.append({"name": img.get("name"), "reason": "could not read JPEG dimensions"})
            continue
        pages_data.append((img, data))
    if not pages_data:
        return {"error": "No embeddable JPEG images", "skipped": skipped}
    n = len(pages_data)
    font_unused = None
    objects: List[Tuple[int, bytes]] = []
    kids = []
    oid = 3
    page_meta = []
    for img, data in pages_data:
        page_id, content_id, image_id = oid, oid + 1, oid + 2
        oid += 3
        page_meta.append((page_id, content_id, image_id, img, data))
        kids.append(f"{page_id} 0 R")
    objects.append((1, b"<< /Type /Catalog /Pages 2 0 R >>"))
    objects.append((2, f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {n} >>".encode("ascii")))
    for page_id, content_id, image_id, img, data in page_meta:
        w, h, comps = _jpeg_size(data) or (1, 1, 3)
        colorspace = "/DeviceGray" if comps == 1 else "/DeviceRGB"
        scale = min((width_pt - 40) / w, (height_pt - 40) / h)
        dw, dh = w * scale, h * scale
        dx = (width_pt - dw) / 2
        dy = (height_pt - dh) / 2
        objects.append((image_id, (f"<< /Type /XObject /Subtype /Image /Width {w} /Height {h} "
                                   f"/ColorSpace {colorspace} /BitsPerComponent 8 /Filter /DCTDecode "
                                   f"/Length {len(data)} >>").encode("ascii") + b"\nstream\n" + data + b"\nendstream"))
        content = f"q {dw:.1f} 0 0 {dh:.1f} {dx:.1f} {dy:.1f} cm /Im0 Do Q"
        cs = content.encode("ascii")
        objects.append((content_id, b"<< /Length " + str(len(cs)).encode() + b" >>\nstream\n" + cs + b"\nendstream"))
        objects.append((page_id, (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width_pt:g} {height_pt:g}] "
                                  f"/Resources << /XObject << /Im0 {image_id} 0 R >> >> "
                                  f"/Contents {content_id} 0 R >>").encode("ascii")))
    pdf = _serialize_pdf(objects)
    return {"pdf_base64": _b64(pdf), "pages": n, "bytes": len(pdf), "skipped": skipped}


def pdf_info(pdf_base64: str) -> Dict[str, Any]:
    """Basic PDF inspection: page count and declared size."""
    data = _unb64(pdf_base64)
    if not data.startswith(b"%PDF"):
        return {"error": "Not a PDF (missing %PDF header)"}
    pages = len(re.findall(rb"/Type\s*/Page[^s]", data))
    version = data[1:8].decode("ascii", "replace")
    producer = re.search(rb"/Producer\s*\(([^)]*)\)", data)
    return {"valid": True, "version": version, "pages": pages, "bytes": len(data),
            "producer": producer.group(1).decode("latin-1") if producer else None}


def brochure_pdf(title: str, subtitle: str = "", sections: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Build a branded text brochure PDF from a list of sections."""
    lines: List[str] = []
    if subtitle:
        lines += [subtitle, ""]
    for sec in sections or []:
        headings = sec.get("heading")
        if headings:
            lines.append(str(headings).upper())
        for item in sec.get("lines", []) or []:
            lines.append(f"  - {item}")
        for row in sec.get("rows", []) or []:
            lines.append("  " + " | ".join(str(c) for c in row))
        lines.append("")
    lines.append("Generated by the Arz-e-Pak Tools & Utilities center")
    return text_to_pdf(title, lines)


def image_resize_plan(width: int, height: int, max_width: int = 1600, max_height: int = 1600) -> Dict[str, Any]:
    """Compute a contain-fit resize target without touching the pixels."""
    if width <= 0 or height <= 0:
        return {"error": "width and height must be greater than zero"}
    ratio = min(max_width / width, max_height / height, 1.0)
    return {"source": {"width": width, "height": height},
            "target": {"width": int(round(width * ratio)), "height": int(round(height * ratio))},
            "scale": _round(ratio, 4), "needed": ratio < 1.0}


CONVERSION_GUIDE: Dict[str, Dict[str, Any]] = {
    "pdf_to_images": {"requires_optional_dependency": True, "recommended": "PyMuPDF (fitz) or pdf2image + Poppler",
                      "note": "Rasterise each page to PNG/JPEG at a chosen DPI."},
    "pdf_merge_split": {"requires_optional_dependency": True, "recommended": "pypdf",
                        "note": "Merge, split, rotate, reorder and compress pages."},
    "ocr": {"requires_optional_dependency": True,
            "recommended": "Tesseract (pytesseract) or a document-AI service",
            "note": "Extract text from scanned property documents; confidence-scored."},
    "docx_to_pdf": {"requires_optional_dependency": True,
                    "recommended": "LibreOffice headless or docx2pdf",
                    "note": "Convert Word documents to PDF."},
    "cad_convert": {"requires_optional_dependency": True, "recommended": "ezdxf (DXF) / ODA File Converter (DWG/DGN)",
                    "note": CAD_FORMAT_NOTE},
}


def convert_guide(kind: str) -> Dict[str, Any]:
    """Explain what a conversion needs (and why) for the heavier file operations."""
    guide = CONVERSION_GUIDE.get((kind or "").lower())
    if not guide:
        return {"error": f"Unknown conversion: {kind}", "kinds": sorted(CONVERSION_GUIDE)}
    return {"kind": kind, **guide,
            "note_uploads": "Treat uploads as untrusted: validate file type, cap size, "
                            "isolate conversion, expire temporary files."}


def document_tools() -> Dict[str, Any]:
    """The document/conversion tools and whether each is native or needs a dependency."""
    rows = [
        {"key": "images_to_pdf", "name": "Images to PDF", "status": "native", "engine": "tools.images_to_pdf"},
        {"key": "text_to_pdf", "name": "Text/listings to PDF", "status": "native", "engine": "tools.text_to_pdf"},
        {"key": "brochure_pdf", "name": "Property brochure maker", "status": "native", "engine": "tools.brochure_pdf"},
        {"key": "pdf_info", "name": "PDF inspect (pages/size)", "status": "native", "engine": "tools.pdf_info"},
        {"key": "image_resize_plan", "name": "Batch image resize planner", "status": "native", "engine": "tools.image_resize_plan"},
    ]
    for key, g in CONVERSION_GUIDE.items():
        rows.append({"key": key, "name": key.replace("_", " ").title(), "status": "optional_dependency",
                     "recommended": g.get("recommended")})
    return {"count": len(rows), "tools": rows}


# ============================================================
# PAKISTAN & ISLAMIC CALENDAR
# ============================================================

_ISLAMIC_EPOCH_JDN = 1948439  # 1 Muharram 1 AH in the civil (tabular) Islamic calendar
_HIJRI_ADJUST_DAYS = 1        # +1 day so the tabular dates track official PK announcements
                              # (still labelled "predicted" - moon sighting can shift by a day)

HIJRI_MONTHS = ["Muharram", "Safar", "Rabi al-Awwal", "Rabi al-Thani", "Jumada al-Awwal",
                "Jumada al-Thani", "Rajab", "Sha'ban", "Ramadan", "Shawwal",
                "Dhu al-Qa'dah", "Dhu al-Hijjah"]

ISLAMIC_OCCASIONS: List[Dict[str, Any]] = [
    {"key": "new_year", "name": "Islamic New Year (1 Muharram)", "month": 1, "day": 1},
    {"key": "ashura", "name": "Ashura (10 Muharram)", "month": 1, "day": 10},
    {"key": "mawlid", "name": "Eid Milad un-Nabi (12 Rabi al-Awwal)", "month": 3, "day": 12},
    {"key": "isra_miraj", "name": "Isra & Mi'raj (27 Rajab)", "month": 7, "day": 27},
    {"key": "shab_e_barat", "name": "Shab-e-Barat (15 Sha'ban)", "month": 8, "day": 15},
    {"key": "ramadan", "name": "Ramadan begins (1 Ramadan)", "month": 9, "day": 1},
    {"key": "shab_e_qadr", "name": "Shab-e-Qadr (27 Ramadan)", "month": 9, "day": 27},
    {"key": "eid_fitr", "name": "Eid-ul-Fitr (1 Shawwal)", "month": 10, "day": 1},
    {"key": "eid_adha", "name": "Eid-ul-Adha (10 Dhu al-Hijjah)", "month": 12, "day": 10},
]


def _gregorian_to_jdn(year: int, month: int, day: int) -> int:
    a = (14 - month) // 12
    y2 = year + 4800 - a
    m2 = month + 12 * a - 3
    return day + (153 * m2 + 2) // 5 + 365 * y2 + y2 // 4 - y2 // 100 + y2 // 400 - 32045


def _jdn_to_gregorian(jdn: int) -> date:
    a = int(jdn) + 32044
    b = (4 * a + 3) // 146097
    c = a - (146097 * b) // 4
    d2 = (4 * c + 3) // 1461
    e = c - (1461 * d2) // 4
    m = (5 * e + 2) // 153
    day = e - (153 * m + 2) // 5 + 1
    month = m + 3 - 12 * (m // 10)
    year = 100 * b + d2 - 4800 + m // 10
    return date(year, month, day)


def _hijri_to_jdn_raw(y: int, m: int, d: int) -> int:
    return (d + math.ceil(29.5 * (m - 1)) + (y - 1) * 354
            + (3 + 11 * y) // 30 + _ISLAMIC_EPOCH_JDN - 1)


def hijri_to_jdn(y: int, m: int, d: int) -> int:
    return _hijri_to_jdn_raw(y, m, d) + _HIJRI_ADJUST_DAYS


def jdn_to_hijri(jdn: int) -> Tuple[int, int, int]:
    jdn = int(jdn) - _HIJRI_ADJUST_DAYS
    year = int((jdn - _ISLAMIC_EPOCH_JDN) / 354.3667) + 1
    while _hijri_to_jdn_raw(year + 1, 1, 1) <= jdn:
        year += 1
    while _hijri_to_jdn_raw(year, 1, 1) > jdn:
        year -= 1
    month = 1
    while month < 12 and _hijri_to_jdn_raw(year, month + 1, 1) <= jdn:
        month += 1
    day = int(jdn - _hijri_to_jdn_raw(year, month, 1)) + 1
    return year, month, day


def hijri_from_gregorian(when: Any) -> Dict[str, Any]:
    """Convert a Gregorian date to its (predicted, tabular) Hijri date."""
    d = _coerce_date(when)
    if d is None:
        return {"error": "Provide a date as YYYY-MM-DD (or a date object)"}
    y, m, day = jdn_to_hijri(_gregorian_to_jdn(d.year, d.month, d.day))
    return {"gregorian": d.isoformat(), "hijri_year": y, "hijri_month": m,
            "hijri_month_name": HIJRI_MONTHS[m - 1], "hijri_day": day,
            "hijri": f"{day} {HIJRI_MONTHS[m - 1]} {y} AH", "calendar": "tabular (civil)"}


def gregorian_from_hijri(year: int, month: int, day: int) -> Dict[str, Any]:
    """Convert a Hijri date to its (predicted) Gregorian date."""
    if not (1 <= month <= 12):
        return {"error": "Hijri month must be 1-12"}
    if not (1 <= day <= 30):
        return {"error": "Hijri day must be 1-30"}
    g = _jdn_to_gregorian(hijri_to_jdn(int(year), int(month), int(day)))
    return {"hijri": f"{day} {HIJRI_MONTHS[month - 1]} {year} AH",
            "hijri_year": year, "hijri_month": month, "hijri_day": day,
            "gregorian": g.isoformat(), "calendar": "tabular (civil)",
            "note": "Official dates can differ by a day or two (moon sighting)."}


def _coerce_date(value: Any) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None
    return None


def islamic_occasions(gregorian_year: int) -> Dict[str, Any]:
    """The main Islamic occasions that fall inside a Gregorian year (predicted)."""
    start = date(int(gregorian_year), 1, 1)
    hy0 = jdn_to_hijri(_gregorian_to_jdn(start.year, start.month, start.day))[0]
    rows = []
    for hy in (hy0, hy0 + 1):
        for occ in ISLAMIC_OCCASIONS:
            g = _jdn_to_gregorian(hijri_to_jdn(hy, occ["month"], occ["day"]))
            if g.year == int(gregorian_year):
                rows.append({"key": occ["key"], "name": occ["name"], "date": g.isoformat(),
                             "hijri": f"{hy}-{occ['month']:02d}-{occ['day']:02d}",
                             "predicted": True, "announced": False})
    rows.sort(key=lambda r: r["date"])
    return {"year": int(gregorian_year), "count": len(rows), "occasions": rows,
            "note": "Predicted from the tabular Islamic calendar. Religious dates depend on "
                    "moon sighting - distinguish officially announced dates from predictions."}


PAKISTAN_FIXED_HOLIDAYS: List[Dict[str, Any]] = [
    {"date": "02-05", "name": "Kashmir Solidarity Day"},
    {"date": "03-23", "name": "Pakistan Day"},
    {"date": "05-01", "name": "Labour Day"},
    {"date": "08-14", "name": "Independence Day"},
    {"date": "11-09", "name": "Iqbal Day"},
    {"date": "12-25", "name": "Quaid-e-Azam Day"},
]


def pakistan_holidays(gregorian_year: int) -> Dict[str, Any]:
    """Pakistan public holidays for a year: fixed national days + predicted Islamic ones."""
    year = int(gregorian_year)
    fixed = [{"name": h["name"], "date": f"{year}-{h['date']}", "type": "national",
              "announced": True} for h in PAKISTAN_FIXED_HOLIDAYS]
    occ = {o["key"]: o["date"] for o in islamic_occasions(year)["occasions"]}
    religious = []
    for key, name, spanning in (("eid_fitr", "Eid-ul-Fitr", 3), ("eid_adha", "Eid-ul-Adha", 3),
                                ("ashura", "Ashura", 2), ("mawlid", "Eid Milad un-Nabi", 1)):
        base = occ.get(key)
        if not base:
            continue
        d0 = date.fromisoformat(base)
        for i in range(spanning):
            day = d0 + timedelta(days=i)
            if day.year == year:
                religious.append({"name": name + (f" (day {i + 1})" if spanning > 1 else ""),
                                  "date": day.isoformat(), "type": "religious",
                                  "predicted": True, "announced": False})
    rows = sorted(fixed + religious, key=lambda r: r["date"])
    return {"year": year, "count": len(rows), "holidays": rows,
            "note": "National days are fixed. Religious holidays are predicted; provincial "
                    "governments may announce extra or regional holidays - verify officially."}


def calendar_ics(events: List[Dict[str, Any]], calendar_name: str = "Arz-e-Pak") -> Dict[str, Any]:
    """Render events as a downloadable iCalendar (.ics) feed."""
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Arz-e-Pak//Tools//EN",
             f"X-WR-CALNAME:{calendar_name}"]
    count = 0
    for e in events or []:
        d = _coerce_date(e.get("date"))
        if not d:
            continue
        title = (e.get("title") or e.get("name") or "Event").replace("\n", " ")
        desc = (e.get("description") or "").replace("\n", " ")
        lines += ["BEGIN:VEVENT", f"UID:{_new_id('evt_')}@arzepak",
                  f"DTSTAMP:{datetime.now().strftime('%Y%m%dT%H%M%SZ')}",
                  f"DTSTART;VALUE=DATE:{d.strftime('%Y%m%d')}",
                  f"DTEND;VALUE=DATE:{(d + timedelta(days=1)).strftime('%Y%m%d')}",
                  f"SUMMARY:{title}"]
        if desc:
            lines.append(f"DESCRIPTION:{desc}")
        lines.append("END:VEVENT")
        count += 1
    lines.append("END:VCALENDAR")
    text = "\r\n".join(lines) + "\r\n"
    return {"ics": text, "events": count, "calendar": calendar_name}


def property_reminders(events: List[Dict[str, Any]], lead_days: int = 7) -> Dict[str, Any]:
    """Turn dated property events into reminders (possession, installments, expiries)."""
    out = []
    today = date.today()
    for e in events or []:
        d = _coerce_date(e.get("date"))
        if not d:
            continue
        remind = d - timedelta(days=int(e.get("lead_days", lead_days)))
        out.append({"title": e.get("title") or e.get("name"), "type": e.get("type"),
                    "date": d.isoformat(), "remind_on": remind.isoformat(),
                    "days_to_event": (d - today).days})
    out.sort(key=lambda r: r["date"])
    return {"count": len(out), "lead_days": lead_days, "reminders": out}


def milestone_calendar(start_date: Any, covered_area: float = 1000.0, floors: int = 1,
                       building_type: str = "house", system: str = "rcc_frame") -> Dict[str, Any]:
    """Date-stamp a construction timeline into a milestone calendar."""
    start = _coerce_date(start_date) or date.today()
    timeline = construction.timeline_estimate(covered_area, floors, building_type, system)
    cursor = start
    events = []
    for phase in timeline["phases"]:
        end = cursor + timedelta(days=phase["days"])
        events.append({"title": phase["name"], "type": "construction",
                       "date": end.isoformat(), "start": cursor.isoformat(),
                       "days": phase["days"], "weight_pct": phase["weight_pct"]})
        cursor = end
    return {"start_date": start.isoformat(), "total_days": timeline["total_days"],
            "handover_date": cursor.isoformat(), "events": events,
            "ics": calendar_ics(events, "Construction milestones")["ics"]}


def possession_schedule(start_date: Any, total_price: float, down_payment: float = 0.0,
                        months: int = 24, frequency: str = "monthly") -> Dict[str, Any]:
    """A booking + installment + possession payment schedule with due dates."""
    start = _coerce_date(start_date) or date.today()
    price = float(total_price or 0.0)
    down = min(float(down_payment or 0.0), price)
    months = max(1, int(months or 1))
    step = 3 if frequency == "quarterly" else 1
    installments = max(1, months // step)
    financed = max(0.0, price - down)
    each = financed / installments
    events = [{"title": "Booking / down payment", "type": "payment", "date": start.isoformat(),
               "amount": _round(down)}]
    for i in range(1, installments + 1):
        due = start + timedelta(days=30 * step * i)
        events.append({"title": f"Installment {i}", "type": "payment", "date": due.isoformat(),
                       "amount": _round(each)})
    events.append({"title": "Possession / handover", "type": "possession",
                   "date": (start + timedelta(days=30 * months)).isoformat(), "amount": 0.0})
    return {"start_date": start.isoformat(), "total_price": _round(price),
            "down_payment": _round(down), "installments": installments,
            "installment_amount": _round(each), "frequency": frequency,
            "events": events, "ics": calendar_ics(events, "Payment schedule")["ics"]}


# ============================================================
# REPORTS & EXPORT STUDIO
# ============================================================


def property_comparison(properties: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Side-by-side comparison of listings with derived price/sqft and yield."""
    rows = []
    for p in properties or []:
        price = float(p.get("price") or 0.0)
        area = float(p.get("area_sqft") or p.get("area") or 0.0)
        rent = float(p.get("monthly_rent") or 0.0)
        ppsf = price / area if area else None
        yld = (rent * 12 / price * 100) if (price and rent) else None
        rows.append({"name": p.get("name") or p.get("title"),
                     "city": p.get("city"), "price": _round(price), "area_sqft": _round(area),
                     "bedrooms": p.get("bedrooms"),
                     "price_per_sqft": _round(ppsf) if ppsf else None,
                     "gross_yield_pct": _round(yld, 3) if yld is not None else None})
    best_value = min((r for r in rows if r["price_per_sqft"]), key=lambda r: r["price_per_sqft"],
                     default=None)
    best_yield = max((r for r in rows if r["gross_yield_pct"] is not None),
                     key=lambda r: r["gross_yield_pct"], default=None)
    return {"count": len(rows), "rows": rows,
            "best_value": best_value["name"] if best_value else None,
            "best_yield": best_yield["name"] if best_yield else None}


def investment_summary(initial_investment: float, annual_cash_flow: float = 0.0,
                       hold_years: int = 10, terminal_value: float = 0.0,
                       loan_amount: float = 0.0, loan_rate: Optional[float] = None) -> Dict[str, Any]:
    """Investment summary built on the accounting ROI engine (with scenarios)."""
    return accounting.roi_analysis(initial_investment, annual_cash_flow=annual_cash_flow,
                                   hold_years=hold_years, terminal_value=terminal_value,
                                   loan_amount=loan_amount, loan_rate=loan_rate)


def plot_inventory(properties: List[Dict[str, Any]], marla_sqft: float = 272.25) -> Dict[str, Any]:
    """Plot inventory: area in sqft / marla / kanal with price per unit."""
    rows = []
    for p in properties or []:
        area = float(p.get("area_sqft") or p.get("area") or 0.0)
        price = float(p.get("price") or 0.0)
        rows.append({"name": p.get("name") or p.get("title"), "city": p.get("city"),
                     "sqft": _round(area), "marla": _round(area / marla_sqft),
                     "kanal": _round(area / (marla_sqft * 20)), "price": _round(price),
                     "price_per_marla": _round(price / (area / marla_sqft)) if area else None})
    return {"count": len(rows), "rows": rows}


def rows_to_csv(rows: List[Dict[str, Any]], columns: Optional[List[str]] = None) -> Dict[str, Any]:
    """Serialise rows of dicts to CSV text (all entities support export)."""
    rows = rows or []
    cols = columns or (sorted({k for r in rows for k in r}) if rows else [])
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow({c: r.get(c) for c in cols})
    return {"columns": cols, "rows": len(rows), "csv": buf.getvalue()}


def rows_to_markdown(rows: List[Dict[str, Any]], columns: Optional[List[str]] = None) -> Dict[str, Any]:
    """Serialise rows of dicts to a Markdown table."""
    rows = rows or []
    cols = columns or (sorted({k for r in rows for k in r}) if rows else [])
    lines = ["| " + " | ".join(cols) + " |",
             "| " + " | ".join("---" for _ in cols) + " |"]
    for r in rows:
        lines.append("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
    return {"columns": cols, "rows": len(rows), "markdown": "\n".join(lines)}


# ============================================================
# TOOLS CENTER CATALOG
# ============================================================

# One card per tool, grouped by the roadmap's categories and launch phases.
TOOL_CATALOG: List[Dict[str, Any]] = [
    {"key": "mortgage", "name": "Mortgage Calculator", "category": "calculators", "phase": 1,
     "blurb": "Estimate monthly payments and total financing cost.", "mcp_tool": "tool_mortgage_calculator"},
    {"key": "installment", "name": "Installment Calculator", "category": "calculators", "phase": 1,
     "blurb": "Monthly installment and down-payment planner.", "mcp_tool": "tool_installment_plan"},
    {"key": "rental_yield", "name": "Rental Yield Calculator", "category": "calculators", "phase": 1,
     "blurb": "Estimate gross and net rental returns.", "mcp_tool": "tool_rental_yield"},
    {"key": "appreciation", "name": "Appreciation & Growth", "category": "calculators", "phase": 1,
     "blurb": "Property appreciation and investment-growth projection.", "mcp_tool": "tool_appreciation"},
    {"key": "area", "name": "Plot Area Converter", "category": "calculators", "phase": 1,
     "blurb": "Convert marla, kanal, square feet and more.", "mcp_tool": "tool_area_convert"},
    {"key": "price_per_unit", "name": "Price per sqft", "category": "calculators", "phase": 1,
     "blurb": "Price per sqft / sqyd / sqm / marla for a listing.", "mcp_tool": "tool_price_per_unit"},
    {"key": "plot_dimensions", "name": "Plot Size & Dimensions", "category": "calculators", "phase": 1,
     "blurb": "Length, width, perimeter and diagonal from area.", "mcp_tool": "tool_plot_dimensions"},
    {"key": "construction", "name": "Construction Cost Estimator", "category": "calculators", "phase": 1,
     "blurb": "Build cost from covered area, quality and city.", "mcp_tool": "tool_construction_cost"},
    {"key": "transfer", "name": "Transfer & Stamp Duty", "category": "calculators", "phase": 1,
     "blurb": "Stamp duty, CVT, registration and mutation estimate.", "mcp_tool": "tool_transfer_costs"},
    {"key": "commission", "name": "Agent Commission", "category": "calculators", "phase": 1,
     "blurb": "Agent commission and VAT on a sale.", "mcp_tool": "tool_agent_commission"},
    {"key": "cgt", "name": "Capital Gains Tax", "category": "calculators", "phase": 1,
     "blurb": "CGT on disposal by holding period and filer status.", "mcp_tool": "tool_capital_gains_tax"},
    {"key": "joint_investment", "name": "Joint Investment Split", "category": "calculators", "phase": 1,
     "blurb": "Profit-sharing between partners pro-rata to capital.", "mcp_tool": "tool_joint_investment"},
    {"key": "georeference", "name": "Georeference a Plan", "category": "gis", "phase": 2,
     "blurb": "Align a scanned plan to geographic coordinates.", "mcp_tool": "tool_georeference"},
    {"key": "map_measure", "name": "Map Measurement", "category": "gis", "phase": 2,
     "blurb": "Measure land area, perimeter and distance.", "mcp_tool": "tool_map_measure"},
    {"key": "coords_area", "name": "Area from Coordinates", "category": "gis", "phase": 2,
     "blurb": "Polygon area from surveyed coordinates.", "mcp_tool": "tool_polygon_area"},
    {"key": "geodata", "name": "GeoJSON / KML Import-Export", "category": "gis", "phase": 2,
     "blurb": "Import and export common GIS formats.", "mcp_tool": "tool_export_geodata"},
    {"key": "aerial", "name": "Aerial Image Compare", "category": "gis", "phase": 2,
     "blurb": "Compare dated imagery and track visible change.", "mcp_tool": "tool_aerial_compare"},
    {"key": "nearby", "name": "Nearby Amenities", "category": "gis", "phase": 2,
     "blurb": "Locate properties and nearby amenities.", "mcp_tool": "tool_locate_nearby"},
    {"key": "cad", "name": "CAD Drawing Preview / Convert", "category": "cad", "phase": 3,
     "blurb": "Preview and convert supported CAD formats.", "mcp_tool": "tool_cad_inspect"},
    {"key": "photo", "name": "Photo Geotagger", "category": "photo", "phase": 2,
     "blurb": "Read, add or view photo GPS coordinates.", "mcp_tool": "tool_read_photo_gps"},
    {"key": "documents", "name": "PDF & Image Converter", "category": "documents", "phase": 1,
     "blurb": "Convert, merge, split and compress documents.", "mcp_tool": "tool_images_to_pdf"},
    {"key": "brochure", "name": "Property Brochure Maker", "category": "documents", "phase": 1,
     "blurb": "Create a shareable PDF from listing details.", "mcp_tool": "tool_brochure_pdf"},
    {"key": "calendar", "name": "Pakistan Holiday Calendar", "category": "calendar", "phase": 1,
     "blurb": "Browse public holidays and Islamic occasions.", "mcp_tool": "tool_pakistan_holidays"},
    {"key": "milestones", "name": "Construction Milestone Calendar", "category": "calendar", "phase": 1,
     "blurb": "Date-stamp a build timeline and export an .ics.", "mcp_tool": "tool_milestone_calendar"},
    {"key": "reports", "name": "Reports & Export Studio", "category": "documents", "phase": 3,
     "blurb": "Comparison reports, inventory, CSV/Excel exports.", "mcp_tool": "tool_property_comparison"},
]

TOOL_CATEGORIES: Dict[str, str] = {
    "calculators": "Calculators", "gis": "GIS & Maps", "cad": "CAD & Plans",
    "photo": "Photo Tools", "documents": "Documents & Reports", "calendar": "Calendar",
}


def tool_categories() -> Dict[str, Any]:
    """The Tools Center categories and how many tools each holds."""
    counts: Dict[str, int] = {}
    for t in TOOL_CATALOG:
        counts[t["category"]] = counts.get(t["category"], 0) + 1
    return {"count": len(TOOL_CATEGORIES),
            "categories": [{"key": k, "label": v, "count": counts.get(k, 0)}
                           for k, v in TOOL_CATEGORIES.items()]}


def find_tool(key: str) -> Optional[Dict[str, Any]]:
    return next((t for t in TOOL_CATALOG if t["key"] == key), None)


def tools_by_category(category: Optional[str] = None, phase: Optional[int] = None) -> List[Dict[str, Any]]:
    rows = [t for t in TOOL_CATALOG
            if (not category or t["category"] == category) and (not phase or t["phase"] == phase)]
    return rows


def tools_overview() -> Dict[str, Any]:
    """Counts by category and phase, plus the native vs optional-dependency split."""
    by_category: Dict[str, int] = {}
    by_phase: Dict[int, int] = {}
    for t in TOOL_CATALOG:
        by_category[t["category"]] = by_category.get(t["category"], 0) + 1
        by_phase[t["phase"]] = by_phase.get(t["phase"], 0) + 1
    native = ["area", "price_per_unit", "plot_dimensions", "map_measure", "coords_area",
              "geodata", "nearby", "photo", "documents", "brochure", "calendar", "reports",
              "milestones", "cad"]
    return {
        "counts": {"tools": len(TOOL_CATALOG), "categories": len(TOOL_CATEGORIES),
                   "calculators": len(calculator_catalog()["calculators"]),
                   "crs_systems": len(crs_catalog()["systems"]),
                   "saved_projects": len(projects_db)},
        "by_category": dict(sorted(by_category.items())),
        "by_phase": {f"phase_{k}": v for k, v in sorted(by_phase.items())},
        "native_tools": sum(1 for t in TOOL_CATALOG if t["key"] in native),
        "optional_dependency_tools": sum(1 for t in TOOL_CATALOG if t["key"] not in native),
        "config": TOOLS_CONFIG,
    }


def tool_view(key: str) -> Dict[str, Any]:
    """A single tool card plus, where useful, its live sample/first-call output."""
    card = find_tool(key)
    if not card:
        return {"error": f"Unknown tool: {key}", "keys": [t["key"] for t in TOOL_CATALOG]}
    return card

