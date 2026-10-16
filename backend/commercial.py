"""Commercialization — products, plans, metering, billing & payouts (framework-free).

Turns the roadmap's *hybrid pricing* into an engine: a product catalogue (the 8
products with P0–P2 priority), subscription plans, per-call usage metering,
entitlements, usage-based billing statements and performance revenue-share payouts.
"""

import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


COMMERCIAL_CONFIG: Dict[str, Any] = {
    "currency": "USD",
    "vat_rate": 0.17,
    "default_unit_price": 0.05,          # per MCP tool call (USD)
    "billing_interval": "monthly",
    "default_platform_share": 0.20,
}

PRICING_MODELS: Dict[str, str] = {
    "subscription": "Per-seat / per-unit recurring subscription",
    "usage": "Pay-per-call / pay-per-lead metered usage",
    "performance": "Performance share (pay-for-closing, rent share)",
    "hybrid": "Subscription + usage overage + optional performance share",
    "license": "Enterprise / white-label licence",
}


def _product(key: str, name: str, priority: str, segment: str, models: List[str],
             positioning: str, agents: List[str], price_from: float,
             unit: str) -> Dict[str, Any]:
    return {"key": key, "name": name, "priority": priority, "segment": segment,
            "pricing_models": models, "positioning": positioning, "agents": agents,
            "price_from": price_from, "unit": unit,
            "model_labels": [PRICING_MODELS.get(m, m) for m in models]}


PRODUCTS: List[Dict[str, Any]] = [
    _product("property_intelligence_mcp", "Property Intelligence MCP Server", "P0",
             "platform / enterprise", ["usage", "license"],
             "Lowest cost, highest leverage: listed in AI-client directories for passive reach.",
             ["property_intelligence_mcp", "anomaly_agent", "seller_pricing_agent"],
             0.05, "per tool call"),
    _product("broker_ai_workspace", "Broker AI Workspace", "P0", "brokerage",
             ["subscription", "hybrid"],
             "Agentic OS for brokers: CRM + transaction + accounting + marketing on one layer.",
             ["broker_workspace", "crm_agent", "transaction_agent", "accounting_agent",
              "marketing_agent", "compliance_agent"],
             99.0, "per seat / month"),
    _product("mcp_for_brokers", "MCP for Brokers", "P0", "brokerage",
             ["subscription", "usage"],
             "Let brokers run the business from Claude / ChatGPT / Cursor.",
             ["mcp_for_brokers"], 29.0, "per seat / month"),
    _product("conversational_homebuying_agent", "Conversational Homebuying Agent", "P1",
             "consumer", ["subscription", "performance"],
             "Conversation-first buying: understand the brief, then recommend and progress.",
             ["conversational_buyer_agent", "anomaly_agent"],
             19.0, "per buyer / month"),
    _product("seller_pricing_marketing_agent", "Seller Intelligent Pricing & Marketing Agent",
             "P1", "consumer / seller", ["subscription", "usage", "performance"],
             "A defensible pricing range and a marketing kit in minutes, not hours.",
             ["seller_pricing_agent", "cma_agent", "staging_agent"],
             39.0, "per listing / month"),
    _product("autonomous_leasing_agent", "Autonomous Leasing Agent", "P1",
             "landlord / PMC", ["subscription", "performance"],
             "24/7 AI leasing, screening, renewals and rent collection on the ledger.",
             ["autonomous_leasing_agent", "renewal_agent", "maintenance_triage_agent"],
             8.0, "per unit / month"),
    _product("agentic_investment_screener", "Agentic Investment Screener", "P2",
             "investor", ["subscription", "performance", "usage"],
             "Screen into the top risk-adjusted returns; watch the exit window.",
             ["investment_screener", "screening_agent", "underwriting_agent"],
             199.0, "per month"),
    _product("ai_marketing_conductor", "AI Marketing Conductor", "P2", "brokerage / marketing",
             ["usage", "hybrid"],
             "Lead generation, routing, qualification and re-engagement as a module.",
             ["marketing_conductor", "lead_engine_agent", "routing_agent", "reengagement_agent"],
             0.0, "per qualified lead"),
]

PLANS: List[Dict[str, Any]] = [
    {"key": "mcp_starter", "product": "property_intelligence_mcp", "name": "MCP Starter",
     "price": 0.0, "interval": "monthly", "included_units": 1000, "overage_rate": 0.05, "seats": 1},
    {"key": "mcp_growth", "product": "property_intelligence_mcp", "name": "MCP Growth",
     "price": 199.0, "interval": "monthly", "included_units": 50000, "overage_rate": 0.035, "seats": 5},
    {"key": "mcp_enterprise", "product": "property_intelligence_mcp", "name": "MCP Enterprise (licence)",
     "price": 2499.0, "interval": "monthly", "included_units": 1000000, "overage_rate": 0.02,
     "seats": 50, "white_label": True},
    {"key": "broker_seat", "product": "broker_ai_workspace", "name": "Broker Workspace",
     "price": 99.0, "interval": "monthly", "included_units": 2000, "overage_rate": 0.04, "seats": 1},
    {"key": "broker_team", "product": "broker_ai_workspace", "name": "Broker Workspace Team",
     "price": 79.0, "interval": "monthly", "included_units": 1500, "overage_rate": 0.035, "seats": 5},
    {"key": "mcp_for_brokers_seat", "product": "mcp_for_brokers", "name": "MCP for Brokers",
     "price": 29.0, "interval": "monthly", "included_units": 5000, "overage_rate": 0.03, "seats": 1},
    {"key": "buyer_priority", "product": "conversational_homebuying_agent", "name": "Buyer Priority",
     "price": 19.0, "interval": "monthly", "included_units": 0, "overage_rate": 0.0, "seats": 1},
    {"key": "seller_listing", "product": "seller_pricing_marketing_agent", "name": "Seller Listing",
     "price": 39.0, "interval": "monthly", "included_units": 10, "overage_rate": 4.0, "seats": 1},
    {"key": "leasing_per_unit", "product": "autonomous_leasing_agent", "name": "Leasing per Unit",
     "price": 8.0, "interval": "monthly", "included_units": 1, "overage_rate": 0.5, "seats": 1},
    {"key": "investor_pro", "product": "agentic_investment_screener", "name": "Investor Pro",
     "price": 199.0, "interval": "monthly", "included_units": 500, "overage_rate": 0.5, "seats": 1},
    {"key": "conductor_lead", "product": "ai_marketing_conductor", "name": "Conductor (per lead)",
     "price": 0.0, "interval": "monthly", "included_units": 0, "overage_rate": 12.0, "seats": 1},
]

GTM_PLAYBOOK: Dict[str, Any] = {
    "priorities": [
        {"tier": "P0", "product": "Property Intelligence MCP Server",
         "reason": "Lowest cost, highest leverage; passive inbound from AI-client directories."},
        {"tier": "P0", "product": "Broker AI Workspace",
         "reason": "Benchmarks validated models; fast ARR growth."},
        {"tier": "P1", "product": "Conversational Homebuying Agent",
         "reason": "Differentiated front-end; drives traffic and conversion."},
        {"tier": "P1", "product": "Autonomous Leasing Agent",
         "reason": "Native accounting + CRM gives clear unit economics."},
        {"tier": "P2", "product": "Agentic Investment Screener",
         "reason": "High ARPU; needs data accumulation and underwriting depth."},
        {"tier": "P2", "product": "AI Marketing Conductor",
         "reason": "SaaS value-add; bundles with CRM for sales."},
    ],
    "principles": [
        {"name": "MCP first", "detail": "Launch the MCP server, then build front-ends around it."},
        {"name": "Accounting + CRM loop is the moat",
         "detail": "Link the transaction lifecycle directly to the financial ledger."},
        {"name": "Agentic OS narrative",
         "detail": "Position each product as a module of an Agentic OS, not an isolated tool."},
        {"name": "Hybrid pricing",
         "detail": "Subscriptions + usage-based fees + performance sharing for predictable ARR with upside."},
    ],
}


# ============================================================
# Models
# ============================================================


class Subscription(BaseModel):
    id: str = Field(default_factory=lambda: "sub_" + uuid.uuid4().hex[:8])
    account: str
    plan_key: str
    product: Optional[str] = None
    seats: int = 1
    status: str = "active"  # active | paused | cancelled
    started_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    cancel_at: Optional[str] = None


class MeterEvent(BaseModel):
    id: str = Field(default_factory=lambda: "evt_" + uuid.uuid4().hex[:8])
    account: str
    product: Optional[str] = None
    tool: str = ""
    units: int = 1
    unit_price: Optional[float] = None
    amount: float = 0.0
    billable: bool = True
    at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


class Payout(BaseModel):
    id: str = Field(default_factory=lambda: "pay_" + uuid.uuid4().hex[:8])
    transaction_id: Optional[str] = None
    payee: str = ""
    role: str = "agent"  # agent | platform | agency
    gross_commission: float = 0.0
    share_pct: float = 0.0
    amount: float = 0.0
    status: str = "accrued"  # accrued | invoiced | paid
    at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


subscriptions_db: List[Subscription] = []
meter_events_db: List[MeterEvent] = []
payouts_db: List[Payout] = []


# ============================================================
# Catalogue
# ============================================================


def product_catalog(category: Optional[str] = None, priority: Optional[str] = None) -> List[Dict[str, Any]]:
    rows = PRODUCTS
    if priority:
        rows = [p for p in rows if p["priority"] == priority]
    if category:
        rows = [p for p in rows if category.lower() in p["segment"].lower()]
    out = []
    for p in rows:
        item = dict(p)
        item["plan_count"] = sum(1 for pl in PLANS if pl["product"] == p["key"])
        out.append(item)
    return out


def find_product(key: str) -> Optional[Dict[str, Any]]:
    return next((p for p in PRODUCTS if p["key"] == key), None)


def plan_catalog(product: Optional[str] = None) -> List[Dict[str, Any]]:
    rows = PLANS if not product else [p for p in PLANS if p["product"] == product]
    return [dict(p) for p in rows]


def find_plan(key: str) -> Optional[Dict[str, Any]]:
    return next((dict(p) for p in PLANS if p["key"] == key), None)


def pricing_matrix() -> Dict[str, Any]:
    rows = []
    for p in PRODUCTS:
        rows.append({"product": p["name"], "key": p["key"], "priority": p["priority"],
                     "models": p["pricing_models"], "from": p["price_from"], "unit": p["unit"]})
    return {"currency": COMMERCIAL_CONFIG["currency"], "models": PRICING_MODELS,
            "rows": rows, "gtm": GTM_PLAYBOOK}


def recommend_package(segment: str, seats: int = 1, expected_calls: int = 0,
                      product: Optional[str] = None) -> Dict[str, Any]:
    """Pick the best-fit plan for a segment and estimate the monthly bill."""
    defs = [w.lower() for w in segment.replace("/", " ").split()]
    candidates: List[Dict[str, Any]] = []
    for plan in PLANS:
        prod = find_product(plan["product"])
        if not prod:
            continue
        if product and plan["product"] != product:
            continue
        haystack = (prod["segment"] + " " + prod["name"]).lower()
        segment_fit = 1.0 if any(w in haystack for w in defs if w) else 0.5
        seat_ok = 1.0 if plan.get("seats", 1) >= seats else 0.0
        usage_cost = max(0, expected_calls - plan["included_units"]) * plan["overage_rate"]
        monthly = plan["price"] * max(seat_ok or plan["price"] == 0, 1) + usage_cost
        if plan.get("seats", 1) < seats and plan["price"] > 0:
            # scale per-seat plans by seat count
            monthly = plan["price"] * seats + usage_cost
        candidates.append({"plan": plan["name"], "plan_key": plan["key"], "product": prod["name"],
                           "monthly_estimate": round(monthly, 2), "included_units": plan["included_units"],
                           "overage_rate": plan["overage_rate"], "fit": segment_fit})
    candidates.sort(key=lambda c: (c["fit"], -c["monthly_estimate"]), reverse=True)
    best = candidates[0] if candidates else None
    return {"segment": segment, "seats": seats, "expected_calls": expected_calls,
            "recommended_plan": best, "alternatives": candidates[:5],
            "currency": COMMERCIAL_CONFIG["currency"]}


# ============================================================
# Subscriptions
# ============================================================


def subscribe(account: str, plan_key: str, seats: int = 1) -> Dict[str, Any]:
    plan = find_plan(plan_key)
    if not plan:
        return {"error": f"Unknown plan: {plan_key}", "plans": [p["key"] for p in PLANS]}
    sub = Subscription(account=account, plan_key=plan_key, product=plan["product"], seats=seats)
    subscriptions_db.append(sub)
    return {"subscription": sub.model_dump(), "plan": plan}


def list_subscriptions(account: Optional[str] = None) -> List[Subscription]:
    rows = subscriptions_db
    if account:
        rows = [s for s in rows if s.account == account]
    return rows


def get_subscription(sub_id: str) -> Optional[Subscription]:
    return next((s for s in subscriptions_db if s.id == sub_id), None)


# ============================================================
# Metering & billing
# ============================================================


def meter_usage(account: str, tool: str, units: int = 1, product: Optional[str] = None,
                unit_price: Optional[float] = None, billable: bool = True) -> Dict[str, Any]:
    price = COMMERCIAL_CONFIG["default_unit_price"] if unit_price is None else float(unit_price)
    evt = MeterEvent(account=account, product=product, tool=tool, units=int(units),
                     unit_price=price, amount=round(price * int(units), 4), billable=billable)
    meter_events_db.append(evt)
    return {"event": evt.model_dump(), "account_total_events": sum(
        1 for e in meter_events_db if e.account == account)}


def usage_summary(account: str, days: int = 30) -> Dict[str, Any]:
    cutoff = datetime.now() - timedelta(days=days)
    rows = [e for e in meter_events_db if e.account == account
            and datetime.fromisoformat(e.at) >= cutoff]
    by_tool: Dict[str, Dict[str, Any]] = {}
    for e in rows:
        t = by_tool.setdefault(e.tool, {"tool": e.tool, "calls": 0, "units": 0, "amount": 0.0})
        t["calls"] += 1
        t["units"] += e.units
        t["amount"] = round(t["amount"] + e.amount, 4)
    total = round(sum(e.amount for e in rows if e.billable), 4)
    return {"account": account, "days": days, "billable_calls": sum(1 for e in rows if e.billable),
            "total_units": sum(e.units for e in rows), "total_amount": total,
            "currency": COMMERCIAL_CONFIG["currency"], "by_tool": list(by_tool.values())}


def bill_account(account: str, plan_key: Optional[str] = None, days: int = 30) -> Dict[str, Any]:
    """Build a usage-based billing statement for an account."""
    sub = next((s for s in subscriptions_db if s.account == account and s.status == "active"), None)
    if plan_key is None and sub:
        plan_key = sub.plan_key
    plan = find_plan(plan_key) if plan_key else None
    usage = usage_summary(account, days)
    units = usage["total_units"]
    lines: List[Dict[str, Any]] = []
    total = 0.0
    if plan:
        seats = sub.seats if sub else 1
        recurring = plan["price"] if plan["price"] == 0 else plan["price"] * max(1, seats)
        lines.append({"description": f"{plan['name']} ({seats} seat(s))", "amount": round(recurring, 2)})
        total += recurring
        included = plan["included_units"]
        overage_units = max(0, units - included)
        if overage_units:
            overage = round(overage_units * plan["overage_rate"], 2)
            lines.append({"description": f"Overage {overage_units} units @ {plan['overage_rate']}",
                          "amount": overage})
            total += overage
    else:
        lines.append({"description": f"Metered usage {units} units",
                      "amount": round(usage["total_amount"], 2)})
        total += usage["total_amount"]
    return {"account": account, "period_days": days, "plan": plan["key"] if plan else None,
            "usage_units": units, "usage_amount": usage["total_amount"],
            "lines": lines, "subtotal": round(total, 2),
            "vat": round(total * COMMERCIAL_CONFIG["vat_rate"], 2),
            "total_due": round(total * (1 + COMMERCIAL_CONFIG["vat_rate"]), 2),
            "currency": COMMERCIAL_CONFIG["currency"], "by_tool": usage["by_tool"]}


# ============================================================
# Performance revenue share & payouts
# ============================================================


def revenue_share(commission_gross: float,
                  policy: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    base = {"platform_share": COMMERCIAL_CONFIG["default_platform_share"],
            "partner_share": round(1 - COMMERCIAL_CONFIG["default_platform_share"], 4)}
    policy = {**base, **(policy or {})}
    if sum(policy.values()) > 1.0001:
        return {"error": "revenue shares exceed 100%", "policy": policy}
    return {"commission_gross": round(float(commission_gross), 2),
            "policy": {k: round(v, 4) for k, v in policy.items()},
            "allocation": {k: round(float(commission_gross) * v, 2) for k, v in policy.items()}}


def record_payout(transaction_id: str, gross_commission: float, payee: str, share_pct: float,
                  role: str = "agent") -> Payout:
    payout = Payout(transaction_id=transaction_id, payee=payee, role=role,
                    gross_commission=round(float(gross_commission), 2),
                    share_pct=round(float(share_pct), 4),
                    amount=round(float(gross_commission) * float(share_pct), 2))
    payouts_db.append(payout)
    return payout


def list_payouts(account: Optional[str] = None, status: Optional[str] = None) -> List[Payout]:
    rows = payouts_db
    if account:
        rows = [p for p in rows if p.payee == account]
    if status:
        rows = [p for p in rows if p.status == status]
    return rows
