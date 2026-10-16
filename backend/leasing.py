"""Autonomous leasing agent (framework-free).

Covers the roadmap's *Autonomous Leasing Agent*: 24/7 cross-channel inquiry
handling, application screening, a rent floor tied to the unit's holding cost
(so a unit is never let at a loss), renewal recommendations and the leasing funnel.

It reuses ``accounting`` for the holding-cost floor, so the leasing agent and the
ledger share one source of truth.
"""

import re
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


LEASING_CONFIG: Dict[str, Any] = {
    "default_rent_floor_margin": 0.03,          # let no lower than cost + 3%
    "channels": ["web_chat", "whatsapp", "sms", "email", "voice"],
    "response_sla_minutes": 5,
    "renewal_notice_days": 90,
    "screening": {"min_income_to_rent": 3.0, "min_score": 60, "conditional_score": 48},
}

INQUIRY_INTENTS: Dict[str, List[str]] = {
    "availability": ["available", "vacant", "still there", "when can", "from when"],
    "price": ["rent", "price", "how much", "deposit", "advance", "charges"],
    "amenities": ["gym", "pool", "backup", "generator", "solar", "lift", "parking", "security"],
    "schools": ["school", "college", "academy", "education"],
    "commute": ["commute", "distance", "travel", "office", "minutes", "traffic"],
    "viewing": ["viewing", "visit", "see it", "tour", "appointment"],
    "application": ["apply", "application", "form", "process", "documents"],
    "maintenance": ["leak", "repair", "broken", "issue", "complaint"],
    "other": [],
}


# ============================================================
# Models
# ============================================================


class RentalUnit(BaseModel):
    id: str = Field(default_factory=lambda: "unit_" + uuid.uuid4().hex[:8])
    property_ref: Optional[str] = None
    title: str = ""
    city: Optional[str] = None
    scheme: Optional[str] = None
    rent: float = 0.0
    deposit: float = 0.0
    bedrooms: Optional[int] = None
    area: Optional[float] = None
    status: str = "listed"  # listed | under_application | let | off_market
    monthly_holding_cost: float = 0.0
    floor_rent: Optional[float] = None
    amenities: List[str] = Field(default_factory=list)
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class RentalInquiry(BaseModel):
    id: str = Field(default_factory=lambda: "inq_" + uuid.uuid4().hex[:8])
    unit_id: Optional[str] = None
    channel: str = "web_chat"
    lang: str = "en"
    message: str = ""
    intent: str = "other"
    entities: Dict[str, Any] = Field(default_factory=dict)
    lead_score: int = 0
    reply: str = ""
    auto_handled: bool = True
    status: str = "answered"  # answered | escalated | viewed | applied
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


class Application(BaseModel):
    id: str = Field(default_factory=lambda: "app_" + uuid.uuid4().hex[:8])
    unit_id: Optional[str] = None
    applicant: str = ""
    monthly_income: float = 0.0
    employment: str = "salaried"  # salaried | self_employed | business | retired | student
    references_count: int = 0
    credit_proxy: int = 70  # 0-100 behavioural proxy
    occupants: int = 1
    pets: bool = False
    move_in_days: int = 15
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


units_db: List[RentalUnit] = []
inquiries_db: List[RentalInquiry] = []
applications_db: List[Application] = []


# ============================================================
# Rent floor & inquiry handling
# ============================================================


def rent_floor(monthly_holding_cost: float, margin: Optional[float] = None) -> Dict[str, Any]:
    """The minimum rent that keeps a unit cash-flow positive."""
    margin = LEASING_CONFIG["default_rent_floor_margin"] if margin is None else float(margin)
    floor = float(monthly_holding_cost) * (1 + margin)
    return {"monthly_holding_cost": round(float(monthly_holding_cost), 2),
            "margin": margin, "rent_floor": round(floor, 2)}


def check_rent_against_floor(rent: float, monthly_holding_cost: float,
                             margin: Optional[float] = None) -> Dict[str, Any]:
    f = rent_floor(monthly_holding_cost, margin)
    ok = float(rent) >= f["rent_floor"]
    return {**f, "rent": round(float(rent), 2), "is_viable": ok,
            "shortfall": round(max(0.0, f["rent_floor"] - float(rent)), 2),
            "message": "rent meets the cost floor" if ok
            else "rent is below the cost floor — do not let at a loss"}


def parse_inquiry(message: str) -> Dict[str, Any]:
    low = (message or "").lower()
    intent = "other"
    for key, words in INQUIRY_INTENTS.items():
        if any(w in low for w in words):
            intent = key
            break
    entities: Dict[str, Any] = {}
    money = re.search(r"([\d,]+)\s*(?:k|thousand)?\s*(?:rent|pkr|rs)?", low)
    beds = re.search(r"(\d+)\s*(?:bed|bedroom|br)", low)
    if beds:
        entities["bedrooms"] = int(beds.group(1))
    days = re.search(r"(\d+)\s*(?:day|days|month|months)", low)
    if days:
        entities["horizon"] = days.group(0)
    urgent = any(w in low for w in ("urgent", "today", "asap", "immediately", "moving"))
    return {"intent": intent, "entities": entities, "urgent": urgent,
            "score": min(100, 40 + (30 if intent in ("viewing", "application", "availability") else 10)
                         + (20 if urgent else 0))}


def draft_reply(unit: Optional[RentalUnit], intent: str, entities: Dict[str, Any],
                context: Optional[Dict[str, Any]] = None, lang: str = "en") -> str:
    context = dict(context or {})
    title = (unit.title if unit else "the property") or "the property"
    rent = f"PKR {unit.rent:,.0f}" if unit and unit.rent else "rent on request"
    if intent == "availability":
        return f"Yes, {title} is available. Monthly rent is {rent}. Shall I arrange a viewing?"
    if intent == "price":
        dep = f" Security deposit {unit.deposit:,.0f}." if unit and unit.deposit else ""
        return f"The monthly rent for {title} is {rent}.{dep} Would you like the full terms?"
    if intent == "amenities":
        am = ", ".join(unit.amenities) if unit and unit.amenities else "backup power, security and parking"
        return f"{title} includes {am}. Anything specific you need?"
    if intent == "schools":
        return f"Near {title} there are several well-rated schools; I can share the nearest options and travel times."
    if intent == "commute":
        walk = context.get("walk_score")
        extra = f" Walk score {walk}." if walk else ""
        return f"Commute details for {title}: I can send drive/walk times to your workplace.{extra}"
    if intent == "viewing":
        return f"I can arrange a viewing of {title} this week — which day suits you?"
    if intent == "application":
        return ("The application needs ID, proof of income and references. I can send the form now and "
                "pre-screen you in minutes.")
    if intent == "maintenance":
        return "Sorry for the trouble — please share the details and photos and I'll raise a repair job right away."
    return f"Thanks for your interest in {title}. Could you tell me your budget and preferred move-in date?"


def handle_inquiry(unit: Optional[RentalUnit], message: str, channel: str = "web_chat",
                   lang: str = "en", context: Optional[Dict[str, Any]] = None,
                   persist: bool = True) -> RentalInquiry:
    parsed = parse_inquiry(message)
    auto = parsed["intent"] not in ("maintenance",) and not (parsed.get("urgent") and parsed["intent"] == "other")
    inq = RentalInquiry(
        unit_id=unit.id if unit else None, channel=channel, lang=lang, message=message,
        intent=parsed["intent"], entities=parsed["entities"], lead_score=parsed["score"],
        reply=draft_reply(unit, parsed["intent"], parsed["entities"], context, lang),
        auto_handled=auto, status="answered" if auto else "escalated",
    )
    if persist:
        inquiries_db.append(inq)
    return inq


# ============================================================
# Application screening
# ============================================================


def screen_application(application: Application, unit: Optional[RentalUnit] = None) -> Dict[str, Any]:
    """Score an application and return a decision with conditions."""
    rent = float(unit.rent) if unit and unit.rent else 0.0
    income = float(application.monthly_income or 0)
    itr = (income / rent) if rent else 0.0
    cfg = LEASING_CONFIG["screening"]

    income_pts = min(45.0, (itr / cfg["min_income_to_rent"]) * 35) if rent else 25.0
    refs_pts = min(15.0, application.references_count * 5)
    credit_pts = application.credit_proxy * 0.25
    employment_pts = {"salaried": 10, "business": 9, "self_employed": 7,
                      "retired": 8, "student": 4}.get(application.employment, 6)
    stability_penalty = -5 if application.move_in_days > 30 else 0
    pets_penalty = -4 if application.pets else 0
    score = round(max(0.0, min(100.0, income_pts + refs_pts + credit_pts + employment_pts
                               + stability_penalty + pets_penalty)), 1)
    if itr < cfg["min_income_to_rent"] and rent:
        decision = "decline" if itr < cfg["min_income_to_rent"] * 0.66 else "conditional"
    elif score >= cfg["min_score"]:
        decision = "approve"
    elif score >= cfg["conditional_score"]:
        decision = "conditional"
    else:
        decision = "decline"
    conditions = []
    if decision == "conditional":
        if itr < cfg["min_income_to_rent"]:
            conditions.append("add a guarantor or larger deposit")
        if application.references_count < 2:
            conditions.append("provide 2 references")
        if application.credit_proxy < 60:
            conditions.append("higher security deposit")
    return {"application_id": application.id, "unit_id": unit.id if unit else None,
            "income_to_rent": round(itr, 2), "score": score, "decision": decision,
            "conditions": conditions,
            "recommended_deposit": round(rent * (2 if decision != "approve" else 1), 2) if rent else None,
            "explanation": [f"income-to-rent {round(itr, 2)}x", f"credit proxy {application.credit_proxy}",
                            f"{application.references_count} reference(s)",
                            f"employment {application.employment}"]}


# ============================================================
# Renewals & funnel
# ============================================================


def renewal_recommendation(lease: Dict[str, Any], market: Optional[Dict[str, Any]] = None,
                           tenant: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Recommend a renewal rent and flag retention risk."""
    market = dict(market or {})
    tenant = dict(tenant or {})
    current = float(lease.get("rent_amount") or 0)
    market_rent = float(market.get("market_rent") or current * 1.08)
    days_to_expiry = float(lease.get("days_to_expiry") or 0)
    hold_rent = current  # keep a good tenant rather than chase the last rupee
    vacant_months = float(market.get("expected_vacancy_months") or 1.0)
    vacancy_cost = market_rent * vacant_months
    arrears = bool(tenant.get("arrears"))
    on_time = float(tenant.get("on_time_payment_rate") or 0.95)
    risk = "low"
    if arrears or on_time < 0.8:
        risk = "high"
    elif on_time < 0.92:
        risk = "medium"
    proposed = current * 1.05
    if market_rent > current * 1.15 and risk == "low":
        proposed = current * 1.10
    proposed = min(proposed, market_rent)
    if risk == "high":
        proposed = current  # hold the rent to keep the tenant
    retention = "retain" if risk in ("low", "medium") else "review"
    return {"current_rent": round(current, 2), "market_rent": round(market_rent, 2),
            "proposed_renewal_rent": round(proposed, 2),
            "uplift_pct": round((proposed - current) / current * 100, 2) if current else 0.0,
            "days_to_expiry": days_to_expiry, "retention_risk": risk,
            "vacancy_cost_if_lost": round(vacancy_cost, 2),
            "recommendation": retention,
            "message": (f"Offer {round(proposed):,.0f} ({retention}). Losing the tenant risks "
                        f"~{round(vacancy_cost):,.0f} of vacancy.")}


def leasing_funnel(inquiries: Optional[List[RentalInquiry]] = None,
                   applications: Optional[List[Application]] = None) -> Dict[str, Any]:
    inqs = inquiries if inquiries is not None else inquiries_db
    apps = applications if applications is not None else applications_db
    by_channel: Dict[str, int] = {}
    by_intent: Dict[str, int] = {}
    for i in inqs:
        by_channel[i.channel] = by_channel.get(i.channel, 0) + 1
        by_intent[i.intent] = by_intent.get(i.intent, 0) + 1
    return {"inquiries": len(inqs), "auto_handled": sum(1 for i in inqs if i.auto_handled),
            "escalated": sum(1 for i in inqs if not i.auto_handled),
            "applications": len(apps),
            "avg_inquiry_score": round(sum(i.lead_score for i in inqs) / len(inqs), 1) if inqs else 0,
            "by_channel": by_channel, "by_intent": by_intent}


def rent_collection_status(leases: List[Dict[str, Any]], invoices: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Simple arrears board for the autonomous rent-collection loop."""
    by_lease: Dict[str, float] = {}
    for inv in invoices:
        if inv.get("lease_id") and inv.get("balance", 0) > 0:
            by_lease[inv["lease_id"]] = by_lease.get(inv["lease_id"], 0) + float(inv["balance"])
    rows = []
    for lease in leases:
        bal = by_lease.get(lease.get("id"), 0.0)
        rows.append({"lease_id": lease.get("id"), "tenant": lease.get("tenant"),
                     "unit": lease.get("unit_label"), "outstanding": round(bal, 2),
                     "status": "in_arrears" if bal > 0 else "current"})
    return {"leases": len(leases), "in_arrears": sum(1 for r in rows if r["status"] == "in_arrears"),
            "total_outstanding": round(sum(r["outstanding"] for r in rows), 2), "rows": rows}
