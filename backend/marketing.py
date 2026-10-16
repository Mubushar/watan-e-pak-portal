"""AI Marketing Conductor (framework-free).

Lead capture across channels, qualification, rule-based routing, re-engagement of
dormant/false-negative leads, content generation and campaign planning — the
roadmap's *AI Marketing Conductor*.

Content generation reuses the seller agent's listing-asset generator, so a listing
has one canonical marketing kit whether it is produced for a seller or a campaign.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

import intelligence


MARKETING_CONFIG: Dict[str, Any] = {
    "inactive_days": 45,
    "reengagement_min_score": 35,
    "channel_quality": {"referral": 0.95, "walk_in": 0.9, "website": 0.7, "portal": 0.72,
                        "call": 0.8, "whatsapp": 0.75, "sms": 0.6, "web_chat": 0.72,
                        "voice": 0.78, "email": 0.65},
    "default_sla_hours": 4,
    "content_kinds": ["listing_description", "social_post", "reel_script", "email",
                      "market_report", "video_script"],
}

LEAD_STAGES = ["new", "contacted", "qualified", "viewing", "negotiation", "won", "lost"]


class LeadRoute(BaseModel):
    id: str = Field(default_factory=lambda: "route_" + uuid.uuid4().hex[:6])
    name: str = ""
    priority: int = 100
    match: Dict[str, Any] = Field(default_factory=dict)  # city / language / price_min / price_max / source / use_type / postcode_prefix
    assign_to_agent_id: Optional[str] = None
    queue: str = "general"
    sla_hours: int = 4
    active: bool = True


class MarketingLead(BaseModel):
    id: str = Field(default_factory=lambda: "mlead_" + uuid.uuid4().hex[:8])
    name: str = ""
    channel: str = "website"
    language: str = "en"
    message: Optional[str] = None
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    city: Optional[str] = None
    use_type: Optional[str] = None
    interest_category: Optional[str] = None
    timeline_months: Optional[int] = None
    engagement: int = 40
    stage: str = "new"
    score: int = 0
    band: str = "cold"
    assigned_agent_id: Optional[str] = None
    queue: Optional[str] = None
    last_contact_days: int = 0
    false_negative: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


class ContentAsset(BaseModel):
    id: str = Field(default_factory=lambda: "asset_" + uuid.uuid4().hex[:8])
    kind: str = "social_post"
    ref: Optional[str] = None
    lang: str = "en"
    body: str = ""
    status: str = "draft"  # draft | approved | published
    requires_approval: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


class Campaign(BaseModel):
    id: str = Field(default_factory=lambda: "cmp_" + uuid.uuid4().hex[:8])
    objective: str = ""
    budget: float = 0.0
    channels: List[str] = Field(default_factory=list)
    days: int = 14
    schedule: List[Dict[str, Any]] = Field(default_factory=list)
    kpis: Dict[str, Any] = Field(default_factory=dict)


routes_db: List[LeadRoute] = []
leads_db: List[MarketingLead] = []
assets_db: List[ContentAsset] = []
campaigns_db: List[Campaign] = []


# ============================================================
# Qualification
# ============================================================


def qualify_lead(lead: MarketingLead) -> Dict[str, Any]:
    base = 25.0
    reasons: List[str] = []
    quality = MARKETING_CONFIG["channel_quality"].get(lead.channel, 0.6)
    base += quality * 25
    if quality >= 0.85:
        reasons.append(f"high-intent channel ({lead.channel})")
    engagement = max(0, min(100, lead.engagement))
    base += engagement * 0.25
    if evidence := (lead.budget_max or lead.budget_min):
        base += 12
        reasons.append(f"budget stated ({evidence:,.0f})")
    if lead.timeline_months is not None:
        if lead.timeline_months <= 3:
            base += 12
            reasons.append("ready within a quarter")
        elif lead.timeline_months <= 6:
            base += 6
    if lead.city:
        base += 5
        reasons.append(f"target city {lead.city}")
    if lead.stage in ("viewing", "negotiation"):
        base += 15
        reasons.append("already viewing / negotiating")
    if lead.last_contact_days > 60:
        base -= 15
        reasons.append("stale contact")
    score = int(max(0.0, min(100.0, base)))
    band = "hot" if score >= 75 else "warm" if score >= 55 else "cool" if score >= 35 else "cold"
    if not reasons:
        reasons.append("limited signals — nurture")
    lead.score = score
    lead.band = band
    return {"id": lead.id, "score": score, "band": band, "reasons": reasons,
            "recommended_action": {"hot": "call immediately and route to a senior agent",
                                   "warm": "assign and call within SLA",
                                   "cool": "add to drip campaign",
                                   "cold": "marketing nurture"}[band]}


# ============================================================
# Routing
# ============================================================


def _rule_matches(rule: LeadRoute, lead: MarketingLead) -> bool:
    m = rule.match or {}
    if not rule.active:
        return False
    if m.get("city") and str(lead.city or "").lower() != str(m["city"]).lower():
        return False
    if m.get("language") and str(lead.language or "").lower() != str(m["language"]).lower():
        return False
    if m.get("source") and lead.channel != m["source"]:
        return False
    if m.get("use_type") and lead.use_type != m["use_type"]:
        return False
    if m.get("price_min") and lead.budget_max and lead.budget_max < m["price_min"]:
        return False
    if m.get("price_max") and lead.budget_min and lead.budget_min > m["price_max"]:
        return False
    return True


def route_lead(lead: MarketingLead, rules: Optional[List[LeadRoute]] = None) -> Dict[str, Any]:
    rules = rules if rules is not None else routes_db
    matched = None
    for rule in sorted(rules, key=lambda r: r.priority):
        if _rule_matches(rule, lead):
            matched = rule
            break
    if matched:
        lead.assigned_agent_id = matched.assign_to_agent_id
        lead.queue = matched.queue
        sla = matched.sla_hours
        name = matched.name
    else:
        lead.queue = "general"
        sla = MARKETING_CONFIG["default_sla_hours"]
        name = "default routing"
    return {"lead_id": lead.id, "matched_rule": name, "queue": lead.queue,
            "assigned_agent_id": lead.assigned_agent_id, "sla_hours": sla}


def add_route(name: str, match: Dict[str, Any], assign_to_agent_id: Optional[str] = None,
              queue: str = "general", priority: int = 100, sla_hours: int = 4) -> LeadRoute:
    rule = LeadRoute(name=name, match=match, assign_to_agent_id=assign_to_agent_id, queue=queue,
                     priority=priority, sla_hours=sla_hours)
    routes_db.append(rule)
    return rule


# ============================================================
# Re-engagement
# ============================================================


def reengagement_candidates(leads: Optional[List[MarketingLead]] = None,
                            inactive_days: Optional[int] = None,
                            min_score: Optional[int] = None) -> Dict[str, Any]:
    leads = leads if leads is not None else leads_db
    inactive_days = inactive_days or MARKETING_CONFIG["inactive_days"]
    min_score = min_score or MARKETING_CONFIG["reengagement_min_score"]
    rows: List[Dict[str, Any]] = []
    for lead in leads:
        dormant = lead.last_contact_days >= inactive_days
        lost = lead.stage == "lost"
        if lead.false_negative or ((dormant or lost) and lead.score >= min_score):
            lead.false_negative = True
            rows.append({
                "id": lead.id, "name": lead.name, "score": lead.score, "band": lead.band,
                "stage": lead.stage, "last_contact_days": lead.last_contact_days,
                "reason": "previously rejected but scores well" if lost
                          else f"dormant {lead.last_contact_days} days",
                "outreach": (f"Hi {lead.name or 'there'}, are you still looking"
                             f"{(' in ' + lead.city) if lead.city else ''}? I have new options that "
                             f"match your budget — shall I send 3?"),
            })
    rows.sort(key=lambda r: r["score"], reverse=True)
    return {"scanned": len(leads), "candidates": len(rows), "revived": rows}


# ============================================================
# Content
# ============================================================


def generate_content(kind: str, listing: Optional[Dict[str, Any]] = None, ref: Optional[str] = None,
                     tone: str = "professional", lang: str = "en",
                     topic: Optional[str] = None) -> ContentAsset:
    listing = dict(listing or {})
    if kind in ("listing_description", "social_post", "reel_script", "video_script"):
        kit = intelligence.generate_listing_assets(listing, lang=lang, tone=tone)
        body = {"listing_description": kit["description"],
                "social_post": kit["social_posts"]["instagram"] + "\n\n" + kit["social_posts"]["facebook"],
                "reel_script": kit["video_script"],
                "video_script": kit["video_script"]}[kind]
    elif kind == "email":
        kit = intelligence.generate_listing_assets(listing, lang=lang, tone=tone)
        body = f"Subject: {kit['email']['subject']}\n\n{kit['email']['body']}"
    elif kind == "market_report":
        topic = topic or listing.get("city") or "the market"
        body = (f"Market Report — {topic}\n\n"
                f"Prices in {topic} continue to firm on steady demand and limited supply. "
                f"Rents are up on last year and yields remain attractive for the "
                f"{listing.get('category', 'residential')} segment. "
                f"Buyers should act on well-priced stock early; sellers should price to target "
                f"for a confident, quick sale.")
    else:
        body = f"{kind}: {topic or 'content'}"
    asset = ContentAsset(kind=kind, ref=ref or listing.get("id"), lang=lang, body=body,
                         requires_approval=True)
    assets_db.append(asset)
    return asset


def approve_content(asset_id: str, approver: str = "user") -> Dict[str, Any]:
    asset = next((a for a in assets_db if a.id == asset_id), None)
    if not asset:
        return {"error": f"Unknown asset: {asset_id}"}
    asset.status = "approved"
    return {"asset": asset.model_dump(), "approved_by": approver}


# ============================================================
# Campaigns & funnel
# ============================================================


def campaign_plan(objective: str, budget: float, channels: List[str], days: int = 14,
                  audience: Optional[int] = None) -> Campaign:
    weights = {"whatsapp": 0.30, "website": 0.25, "instagram": 0.15, "facebook": 0.12,
               "sms": 0.10, "email": 0.08}
    channels = channels or ["whatsapp", "website", "instagram"]
    total_w = sum(weights.get(c, 1.0 / len(channels)) for c in channels) or 1.0
    allocation = [{"channel": c, "budget": round(budget * weights.get(c, 1.0 / len(channels)) / total_w, 2)}
                  for c in channels]
    cpl = 220.0  # indicative cost per qualified lead (PKR)
    expected_leads = round(budget / cpl)
    schedule = [{"day": d + 1,
                 "channel": channels[d % len(channels)],
                 "action": ["launch creative", "retarget engaged", "post market update",
                            "lead follow-up"][d % 4]}
                for d in range(min(days, 14))]
    kpis = {"expected_leads": expected_leads, "cost_per_lead": cpl,
            "target_qualified_rate": 0.35,
            "expected_qualified": round(expected_leads * 0.35),
            "audience": audience}
    cmp = Campaign(objective=objective, budget=float(budget), channels=channels, days=days,
                   schedule=schedule, kpis=kpis)
    campaigns_db.append(cmp)
    return cmp


def funnel_stats(leads: Optional[List[MarketingLead]] = None) -> Dict[str, Any]:
    leads = leads if leads is not None else leads_db
    by_stage = {s: sum(1 for l in leads if l.stage == s) for s in LEAD_STAGES}
    by_band = {b: sum(1 for l in leads if l.band == b) for b in ("hot", "warm", "cool", "cold")}
    by_channel: Dict[str, int] = {}
    for l in leads:
        by_channel[l.channel] = by_channel.get(l.channel, 0) + 1
    qualified = by_stage.get("qualified", 0) + by_stage.get("viewing", 0) + by_stage.get("negotiation", 0)
    won = by_stage.get("won", 0)
    return {"leads": len(leads), "by_stage": by_stage, "by_band": by_band,
            "by_channel": by_channel, "qualified": qualified, "won": won,
            "conversion_pct": round(100.0 * won / len(leads), 1) if leads else 0.0}
