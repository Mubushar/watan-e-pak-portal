"""Agentic OS — the AI agent layer of the portal (framework-free).

The portal is positioned as an *Agentic Operating System*: rather than isolated
tools, it exposes a catalogue of **agents** that act across the CRM, accounting,
GIS, transactions, leasing, marketing, construction and maintenance modules on one
shared data layer.

This module owns:

* the agent catalogue (the 8 roadmap products + specialist sub-agents),
* the run engine — ``plan → execute → review → deliver`` with approval gates,
* human-in-the-loop **Smart Actions** prioritisation, and
* intent-scoring models (move-likelihood, seller intent, contact priority).

It is deliberately free of MCP/FastAPI code: the server layer supplies the data and
a tool *dispatcher*, so the exact same engine powers MCP tools and REST.
"""

import re
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field


AGENTIC_CONFIG: Dict[str, Any] = {
    "default_autonomy": "assist",
    "autonomy_levels": ["suggest", "assist", "autonomous"],
    "approval_required_levels": ["suggest", "assist"],
    "summary_chars": 480,
    "smart_action_sla_hours": {"urgent": 4, "high": 24, "normal": 72},
    "orchestration_max_agents": 6,
}

MOVE_LIKELIHOOD_WEIGHTS: Dict[str, float] = {
    "life_event": 0.26, "tenure": 0.14, "engagement": 0.18,
    "financial_ready": 0.16, "market_signal": 0.12, "recency": 0.14,
}

SELLER_INTENT_WEIGHTS: Dict[str, float] = {
    "equity": 0.22, "holding_time": 0.16, "market_heat": 0.16,
    "life_event": 0.18, "fsbo_signal": 0.14, "engagement": 0.14,
}


def _agent(
    key: str, name: str, product: Optional[str], category: str, priority: str,
    autonomy: str, summary: str, tools: List[str], inputs: List[str], outputs: List[str],
    channels: Optional[List[str]] = None, kpis: Optional[Dict[str, Any]] = None,
    requires_approval: Optional[bool] = None, handoffs: Optional[List[str]] = None,
    description: Optional[str] = None, workflow: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    return {
        "key": key, "name": name, "product": product, "category": category,
        "priority": priority, "autonomy": autonomy, "summary": summary, "tools": tools,
        "inputs": inputs, "outputs": outputs, "channels": channels or ["in_app"],
        "kpis": kpis or {}, "requires_approval": bool(
            requires_approval if requires_approval is not None
            else autonomy in AGENTIC_CONFIG["approval_required_levels"]),
        "handoffs": handoffs or [], "description": description or summary,
        "workflow": workflow,
    }


# ============================================================
# Agent catalogue — 8 product agents + specialist sub-agents
# ============================================================

AGENTS: List[Dict[str, Any]] = [
    # ---- P0: MCP product line ----
    _agent(
        "property_intelligence_mcp", "Property Intelligence MCP Server",
        "property_intelligence_mcp", "platform", "P0", "autonomous",
        "Exposes the portal's data as pay-per-call MCP tools for external AI clients.",
        ["gis_score", "accounting_snapshot", "market_intelligence", "score_seller_intent",
         "pricing_cma", "anomaly_scan"],
        ["address / region / property_id / contact_id"],
        ["GIS score, financial snapshot, market trend, intent score"],
        channels=["mcp"], requires_approval=False, handoffs=["seller_pricing_agent"],
        kpis={"unit": "tool_call", "target_latency_ms": 400},
    ),
    _agent(
        "mcp_for_brokers", "MCP for Brokers",
        "mcp_for_brokers", "platform", "P0", "autonomous",
        "Lets brokers run CRM, accounting and GIS from Claude / ChatGPT / Cursor.",
        ["search_contacts", "get_commission_projection", "analyze_property_gis",
         "create_listing_draft", "transaction_progress", "smart_actions"],
        ["broker account", "natural-language request"],
        ["contacts, commissions, property scores, listing drafts, tasks"],
        channels=["mcp"], requires_approval=False,
        kpis={"unit": "tool_call", "target_adoption": "monthly active brokers"},
    ),

    # ---- P0: Broker AI Workspace ----
    _agent(
        "broker_workspace", "Broker AI Workspace",
        "broker_ai_workspace", "broker", "P0", "assist",
        "An Agentic OS for brokers: CRM, transaction, accounting and marketing agents.",
        ["smart_actions", "move_likelihood", "transaction_terms_extract",
         "transaction_deadlines", "commission_projection", "marketing_generate_content"],
        ["broker, pipeline, transactions"], ["prioritised actions, drafts, deadlines"],
        channels=["in_app", "email"], handoffs=["crm_agent", "transaction_agent",
                                                "accounting_agent", "marketing_agent"],
        kpis={"target_growth": "6x", "target_deal_lift": "3x"},
        workflow=[
            {"name": "morning_brief", "tool": "smart_actions", "requires_approval": False},
            {"name": "score_contacts", "tool": "move_likelihood", "requires_approval": False},
            {"name": "extract_contracts", "tool": "transaction_terms_extract", "requires_approval": False},
            {"name": "check_deadlines", "tool": "transaction_deadlines", "requires_approval": False},
            {"name": "commission_projection", "tool": "commission_projection", "requires_approval": False},
            {"name": "draft_marketing", "tool": "marketing_generate_content", "requires_approval": True},
            {"name": "human_review", "tool": None, "requires_approval": True},
            {"name": "deliver", "tool": None, "requires_approval": False},
        ],
    ),
    _agent(
        "crm_agent", "CRM Agent", "broker_ai_workspace", "broker", "P0", "assist",
        "Watches contact lifecycle events, scores move-likelihood and drafts outreach.",
        ["move_likelihood", "search_contacts", "outreach_draft"],
        ["contact history", "lifecycle events"], ["move score, outreach message, next action"],
        handoffs=["marketing_agent"],
    ),
    _agent(
        "transaction_agent", "Transaction Agent", "broker_ai_workspace", "broker", "P0", "assist",
        "Extracts contract terms, creates transactions, tracks every deadline and signatures.",
        ["transaction_terms_extract", "transaction_create", "transaction_deadlines",
         "transaction_verify_signatures"],
        ["contract document", "offer details"], ["transaction record, deadline calendar, signature status"],
        requires_approval=True, handoffs=["compliance_agent", "accounting_agent"],
    ),
    _agent(
        "accounting_agent", "Accounting Agent", "broker_ai_workspace", "broker", "P0", "assist",
        "Tracks commissions, posts to the ledger and keeps statements current on close.",
        ["commission_projection", "accounting_snapshot", "revenue_share", "bill_account"],
        ["chosen plan, closed deals"], ["commission statements, invoices"],
        requires_approval=False, handoffs=["commercial_agent"],
    ),
    _agent(
        "marketing_agent", "Marketing Agent", "broker_ai_workspace", "marketing", "P0", "assist",
        "Generates social posts, reels and market reports from listing photos; human approves.",
        ["marketing_generate_content", "campaign_plan"],
        ["listing media", "brand kit"], ["draft content assets"],
        requires_approval=True,
    ),

    # ---- P1: Conversational buyer + seller ----
    _agent(
        "conversational_buyer_agent", "Conversational Homebuying Agent",
        "conversational_homebuying_agent", "buyer_side", "P1", "assist",
        "Understands a buyer's brief in natural language, then recommends and progresses.",
        ["buyer_parse_requirement", "buyer_recommend", "buyer_anomaly_scan",
         "buyer_affordability", "schedule_viewing", "create_offer"], 
        ["budget, timeline, commute, family structure"],
        ["shortlist, scored rationale, affordability, viewing plan, offer draft"],
        channels=["web_chat", "whatsapp", "voice"],
        handoffs=["anomaly_agent", "transaction_agent"],
        workflow=[
            {"name": "parse_requirement", "tool": "buyer_parse_requirement", "requires_approval": False},
            {"name": "recommend", "tool": "buyer_recommend", "requires_approval": False},
            {"name": "find_bargains", "tool": "buyer_anomaly_scan", "requires_approval": False},
            {"name": "affordability", "tool": "buyer_affordability", "requires_approval": False},
            {"name": "human_review", "tool": None, "requires_approval": True},
            {"name": "deliver", "tool": None, "requires_approval": False},
        ],
    ),
    _agent(
        "anomaly_agent", "Bargain / Anomaly Agent", "conversational_homebuying_agent",
        "buyer_side", "P1", "autonomous",
        "Z-score scans the market for positive price deviations below the area average.",
        ["anomaly_scan", "market_intelligence"],
        ["candidate pool", "area averages"], ["underpriced properties with z-scores"],
        requires_approval=False,
    ),
    _agent(
        "seller_pricing_agent", "Seller Intelligent Pricing & Marketing Agent",
        "seller_pricing_marketing_agent", "seller_side", "P1", "assist",
        "Turns an address into a pricing range, confidence level and marketing kit.",
        ["seller_cma", "seller_net_proceeds", "seller_marketing_assets"],
        ["address, property attributes"], ["price range, confidence, marketing assets"],
        channels=["in_app", "email"], handoffs=["cma_agent", "staging_agent", "marketing_agent"],
        workflow=[
            {"name": "pull_comps", "tool": "seller_cma", "requires_approval": False},
            {"name": "net_proceeds", "tool": "seller_net_proceeds", "requires_approval": False},
            {"name": "marketing_kit", "tool": "seller_marketing_assets", "requires_approval": True},
            {"name": "human_review", "tool": None, "requires_approval": True},
            {"name": "deliver", "tool": None, "requires_approval": False},
        ],
    ),
    _agent(
        "cma_agent", "CMA Agent", "seller_pricing_marketing_agent", "seller_side", "P1", "assist",
        "Adjusts comparable sales and produces a defensible pricing range in seconds.",
        ["seller_cma"], ["subject property", "comparable sales"],
        ["adjusted comps, price band, confidence, expected days-on-market"],
    ),
    _agent(
        "staging_agent", "Virtual Staging Agent", "seller_pricing_marketing_agent", "seller_side", "P1", "assist",
        "Suggests virtual staging and generates drone-style video scripts from photos.",
        ["seller_marketing_assets"], ["photos"], ["staging suggestions, video script"],
        requires_approval=True,
    ),

    # ---- P1: Autonomous leasing ----
    _agent(
        "autonomous_leasing_agent", "Autonomous Leasing Agent", "autonomous_leasing_agent",
        "landlord", "P1", "autonomous",
        "Answers rental inquiries 24/7 across channels, screens applicants and renews.",
        ["leasing_inquiry", "leasing_screen_application", "rent_floor",
         "leasing_renewals", "rent_collection"],
        ["rental units", "inquiry"], ["replies, applications, renewals, collection status"],
        channels=["web_chat", "whatsapp", "sms", "email", "voice"],
        requires_approval=False, handoffs=["renewal_agent", "maintenance_triage_agent"],
        workflow=[
            {"name": "answer_inquiry", "tool": "leasing_inquiry", "requires_approval": False},
            {"name": "check_rent_floor", "tool": "rent_floor", "requires_approval": False},
            {"name": "screen_application", "tool": "leasing_screen_application", "requires_approval": False},
            {"name": "renewals", "tool": "leasing_renewals", "requires_approval": False},
            {"name": "deliver", "tool": None, "requires_approval": False},
        ],
    ),
    _agent(
        "renewal_agent", "Renewal Agent", "autonomous_leasing_agent", "landlord", "P1", "autonomous",
        "Recommends renewal rents and retention actions before leases expire.",
        ["leasing_renewals", "market_intelligence"],
        ["lease", "market rents", "tenant history"], ["renewal rent, retention risk, message"],
        requires_approval=False,
    ),
    _agent(
        "maintenance_triage_agent", "Maintenance Triage Agent", "autonomous_leasing_agent",
        "landlord", "P1", "autonomous",
        "Classifies tenant repair reports and routes them to the maintenance wing.",
        ["maintenance_defect", "maintenance_repair_estimate", "maintenance_work_order_create"],
        ["tenant report"], ["defect, priority, work order, cost estimate"],
        requires_approval=False,
    ),

    # ---- P2: Investment screener ----
    _agent(
        "investment_screener", "Agentic Investment Screener", "agentic_investment_screener",
        "investor", "P2", "assist",
        "Screens properties into the top risk-adjusted returns and watches the exit window.",
        ["investment_screen", "investment_underwrite", "investment_portfolio_alerts"],
        ["criteria, capital, portfolio"], ["shortlist, underwritten returns, alerts"],
        handoffs=["screening_agent", "underwriting_agent"],
        workflow=[
            {"name": "screen", "tool": "investment_screen", "requires_approval": False},
            {"name": "underwrite", "tool": "investment_underwrite", "requires_approval": False},
            {"name": "portfolio_alerts", "tool": "investment_portfolio_alerts", "requires_approval": False},
            {"name": "human_review", "tool": None, "requires_approval": True},
            {"name": "deliver", "tool": None, "requires_approval": False},
        ],
    ),
    _agent(
        "screening_agent", "Screening Agent", "agentic_investment_screener", "investor", "P2", "assist",
        "Filters a candidate pool to the top risk-adjusted opportunities.",
        ["investment_screen"], ["candidates", "criteria"], ["ranked shortlist"],
    ),
    _agent(
        "underwriting_agent", "Underwriting Agent", "agentic_investment_screener", "investor", "P2", "assist",
        "Computes after-tax cash flow, IRR, DSCR and valuation for a deal.",
        ["investment_underwrite"], ["deal inputs"], ["underwriting report"],
    ),

    # ---- P2: Marketing conductor ----
    _agent(
        "marketing_conductor", "AI Marketing Conductor", "ai_marketing_conductor",
        "marketing", "P2", "assist",
        "Coordinates lead generation, routing, qualification and re-engagement.",
        ["marketing_qualify_lead", "marketing_route_lead", "marketing_reengagement",
         "marketing_generate_content", "marketing_campaign_plan"],
        ["leads, rules, inventory"], ["qualified leads, routed queue, revived leads, content"],
        handoffs=["lead_engine_agent", "routing_agent", "reengagement_agent", "marketing_agent"],
        workflow=[
            {"name": "qualify", "tool": "marketing_qualify_lead", "requires_approval": False},
            {"name": "route", "tool": "marketing_route_lead", "requires_approval": False},
            {"name": "reengage", "tool": "marketing_reengagement", "requires_approval": False},
            {"name": "content", "tool": "marketing_generate_content", "requires_approval": True},
            {"name": "human_review", "tool": None, "requires_approval": True},
            {"name": "deliver", "tool": None, "requires_approval": False},
        ],
    ),
    _agent(
        "lead_engine_agent", "Lead Engine Agent", "ai_marketing_conductor", "marketing", "P2", "assist",
        "Holds cross-channel 24/7 conversations and qualifies inbound leads.",
        ["marketing_qualify_lead"], ["message, channel"], ["qualification score, next action"],
    ),
    _agent(
        "routing_agent", "Routing Agent", "ai_marketing_conductor", "marketing", "P2", "autonomous",
        "Routes leads by postcode, language, price range and source.",
        ["marketing_route_lead"], ["lead", "rules"], ["assignee, queue, SLA"],
        requires_approval=False,
    ),
    _agent(
        "reengagement_agent", "Re-engagement Agent", "ai_marketing_conductor", "marketing", "P2", "autonomous",
        "Mines dormant leads, flags false negatives and reactivates them.",
        ["marketing_reengagement"], ["dormant leads"], ["revived leads, drafted outreach"],
        requires_approval=False,
    ),

    # ---- Cross-wing specialist ----
    _agent(
        "construction_advisor_agent", "Construction Advisor Agent", "broker_ai_workspace",
        "broker", "P1", "assist",
        "Bridges the construction wing: technique, cost, timeline and impact advice.",
        ["construction_advisory", "construction_estimate", "construction_impact"],
        ["plot, soil, budget"], ["technique, cost estimate, value impact"],
    ),
    _agent(
        "compliance_agent", "Compliance Agent", "broker_ai_workspace", "broker", "P0", "assist",
        "Checks listings, KYC/AML and transaction documents against RERA and policy.",
        ["compliance_check", "transaction_verify_signatures"],
        ["listing", "parties", "documents"], ["pass/fail, findings, required documents"],
        requires_approval=True,
    ),
]

AGENTS_BY_KEY: Dict[str, Dict[str, Any]] = {a["key"]: a for a in AGENTS}

PRODUCTS: List[Dict[str, Any]] = [
    {"key": "property_intelligence_mcp", "name": "Property Intelligence MCP Server",
     "priority": "P0", "category": "platform", "agents": ["property_intelligence_mcp",
     "seller_pricing_agent", "anomaly_agent"]},
    {"key": "broker_ai_workspace", "name": "Broker AI Workspace",
     "priority": "P0", "category": "broker", "agents": ["broker_workspace", "crm_agent",
     "transaction_agent", "accounting_agent", "marketing_agent", "compliance_agent",
     "construction_advisor_agent"]},
    {"key": "mcp_for_brokers", "name": "MCP for Brokers", "priority": "P0",
     "category": "platform", "agents": ["mcp_for_brokers"]},
    {"key": "conversational_homebuying_agent", "name": "Conversational Homebuying Agent",
     "priority": "P1", "category": "buyer_side", "agents": ["conversational_buyer_agent",
     "anomaly_agent"]},
    {"key": "seller_pricing_marketing_agent", "name": "Seller Intelligent Pricing & Marketing Agent",
     "priority": "P1", "category": "seller_side", "agents": ["seller_pricing_agent",
     "cma_agent", "staging_agent"]},
    {"key": "autonomous_leasing_agent", "name": "Autonomous Leasing Agent", "priority": "P1",
     "category": "landlord", "agents": ["autonomous_leasing_agent", "renewal_agent",
     "maintenance_triage_agent"]},
    {"key": "agentic_investment_screener", "name": "Agentic Investment Screener",
     "priority": "P2", "category": "investor", "agents": ["investment_screener",
     "screening_agent", "underwriting_agent"]},
    {"key": "ai_marketing_conductor", "name": "AI Marketing Conductor", "priority": "P2",
     "category": "marketing", "agents": ["marketing_conductor", "lead_engine_agent",
     "routing_agent", "reengagement_agent", "marketing_agent"]},
]


# ============================================================
# Models
# ============================================================


class AgentStep(BaseModel):
    seq: int
    name: str
    capability: Optional[str] = None
    tool: Optional[str] = None
    args: Dict[str, Any] = Field(default_factory=dict)
    status: str = "pending"  # pending | running | done | skipped | failed | awaiting_approval
    requires_approval: bool = False
    approved_by: Optional[str] = None
    output: Optional[str] = None


class AgentRun(BaseModel):
    id: str = Field(default_factory=lambda: "run_" + uuid.uuid4().hex[:10])
    agent_key: str
    objective: str = ""
    subject_type: Optional[str] = None
    subject_id: Optional[str] = None
    context: Dict[str, Any] = Field(default_factory=dict)
    status: str = "queued"  # queued | running | awaiting_approval | approved | completed | failed
    steps: List[AgentStep] = Field(default_factory=list)
    approvals: List[Dict[str, Any]] = Field(default_factory=list)
    outcome: Dict[str, Any] = Field(default_factory=dict)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None


runs_db: List[AgentRun] = []


# ============================================================
# Catalogue access
# ============================================================


def agent_catalog(category: Optional[str] = None, product: Optional[str] = None,
                  priority: Optional[str] = None, autonomy: Optional[str] = None) -> List[Dict[str, Any]]:
    rows = AGENTS
    if category:
        rows = [a for a in rows if a["category"] == category]
    if product:
        rows = [a for a in rows if a["product"] == product]
    if priority:
        rows = [a for a in rows if a["priority"] == priority]
    if autonomy:
        rows = [a for a in rows if a["autonomy"] == autonomy]
    return [agent_view(a) for a in rows]


def find_agent(key: str) -> Optional[Dict[str, Any]]:
    if not key:
        return None
    k = str(key).strip().lower()
    return AGENTS_BY_KEY.get(k) or next(
        (a for a in AGENTS if a["name"].lower() == k), None)


def agent_view(agent: Dict[str, Any]) -> Dict[str, Any]:
    view = dict(agent)
    view["workflow_steps"] = len(_workflow(agent))
    view["tool_count"] = len(agent.get("tools", []))
    return view


def agent_products(priority: Optional[str] = None) -> List[Dict[str, Any]]:
    rows = PRODUCTS
    if priority:
        rows = [p for p in rows if p["priority"] == priority]
    out = []
    for p in rows:
        item = dict(p)
        item["agent_count"] = len(p["agents"])
        out.append(item)
    return out


def agentic_overview() -> Dict[str, Any]:
    by_category: Dict[str, int] = {}
    by_autonomy: Dict[str, int] = {}
    by_priority: Dict[str, int] = {}
    for a in AGENTS:
        by_category[a["category"]] = by_category.get(a["category"], 0) + 1
        by_autonomy[a["autonomy"]] = by_autonomy.get(a["autonomy"], 0) + 1
        by_priority[a["priority"]] = by_priority.get(a["priority"], 0) + 1
    return {
        "config": AGENTIC_CONFIG,
        "counts": {"agents": len(AGENTS), "products": len(PRODUCTS),
                   "autonomous": by_autonomy.get("autonomous", 0),
                   "runs_recorded": len(runs_db)},
        "by_category": by_category, "by_autonomy": by_autonomy, "by_priority": by_priority,
        "products": agent_products(),
    }


# ============================================================
# Run engine
# ============================================================


def _workflow(agent: Dict[str, Any]) -> List[Dict[str, Any]]:
    if agent.get("workflow"):
        return agent["workflow"]
    # Look first, act after the human gate: tools that only read or analyse run before the
    # review; tools that create, send or change something run only once it is approved.
    tools = list(agent.get("tools", []))
    reads = [t for t in tools if not WRITE_TOOL.search(t)]
    writes = [t for t in tools if WRITE_TOOL.search(t)]
    steps: List[Dict[str, Any]] = [
        {"name": "intake", "tool": None, "capability": "understand the request",
         "requires_approval": False}]
    for tool in reads:
        steps.append({"name": tool, "tool": tool,
                      "capability": tool.replace("_", " "), "requires_approval": False})
    steps.append({"name": "review", "tool": None, "capability": "human review",
                  "requires_approval": bool(agent.get("requires_approval"))})
    for tool in writes:
        steps.append({"name": tool, "tool": tool,
                      "capability": tool.replace("_", " "), "requires_approval": False})
    steps.append({"name": "deliver", "tool": None, "capability": "deliver the result",
                  "requires_approval": False})
    return steps


# Tool names that change the portal or reach people outside it.
WRITE_TOOL = re.compile(r"(^|_)(create|send|update|delete|publish|assign|book|schedule|sign|post|dispatch|record|"
                        r"convert|transfer|pay|notify|message|email|whatsapp|add|log|apply|renew)(_|s?$)")


def plan_run(agent_key: str, objective: str = "", subject_type: Optional[str] = None,
             subject_id: Optional[str] = None, context: Optional[Dict[str, Any]] = None,
             args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Create (but do not execute) a run for an agent — the explicit action plan."""
    agent = find_agent(agent_key)
    if not agent:
        return {"error": f"Unknown agent: {agent_key}",
                "keys": [a["key"] for a in AGENTS]}
    base_args = dict(args or {})
    steps = [
        AgentStep(seq=i + 1, name=s["name"], capability=s.get("capability"),
                  tool=s.get("tool"), requires_approval=bool(s.get("requires_approval")),
                  args=dict(base_args))
        for i, s in enumerate(_workflow(agent))
    ]
    run = AgentRun(agent_key=agent["key"], objective=objective, subject_type=subject_type,
                   subject_id=subject_id, context=dict(context or {}), steps=steps,
                   status="queued")
    return run_view(run)


def _summarise(value: Any, chars: int = AGENTIC_CONFIG["summary_chars"]) -> str:
    import json
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001 - best-effort summary
        text = str(value)
    return text[:chars]


def run_agent(agent_key: str, objective: str = "",
              dispatch: Optional[Callable[[str, Dict[str, Any]], Any]] = None,
              context: Optional[Dict[str, Any]] = None, args: Optional[Dict[str, Any]] = None,
              subject_type: Optional[str] = None, subject_id: Optional[str] = None,
              approve: bool = False, persist: bool = True) -> Dict[str, Any]:
    """Plan and execute an agent run.

    Steps marked ``requires_approval`` (sending messages, publishing, changing deals) pause the
    run until a person approves it with :func:`approve_run`; ``approve=True`` pre-approves them
    (scheduled jobs the portal itself runs).

    ``dispatch(tool_name, args)`` is supplied by the server so the engine can call
    the real portal functions; when it is ``None`` the tool steps are *skipped*
    (the run still plans and audits), which is useful for dry runs.
    """
    agent = find_agent(agent_key)
    if not agent:
        return {"error": f"Unknown agent: {agent_key}", "keys": [a["key"] for a in AGENTS]}
    base_args = dict(args or {})
    steps = [
        AgentStep(seq=i + 1, name=s["name"], capability=s.get("capability"),
                  tool=s.get("tool"), requires_approval=bool(s.get("requires_approval")),
                  args=dict(base_args))
        for i, s in enumerate(_workflow(agent))
    ]
    run = AgentRun(agent_key=agent["key"], objective=objective, subject_type=subject_type,
                   subject_id=subject_id, context=dict(context or {}), steps=steps,
                   status="running")
    _execute(run, dispatch, approve)
    if persist:
        runs_db.append(run)
    return run_view(run)


def resume_run(run_id: str, dispatch: Optional[Callable[[str, Dict[str, Any]], Any]] = None,
               approve: bool = False) -> Dict[str, Any]:
    run = next((r for r in runs_db if r.id == run_id), None)
    if not run:
        return {"error": f"Unknown run: {run_id}"}
    if run.status in ("completed", "failed"):
        return run_view(run)
    run.status = "running"
    _execute(run, dispatch, approve)
    return run_view(run)


def _execute(run: AgentRun, dispatch: Optional[Callable[[str, Dict[str, Any]], Any]],
             approve: bool) -> None:
    for step in run.steps:
        if step.status in ("done", "skipped"):
            continue
        if step.requires_approval and step.status != "approved" and not approve:
            step.status = "awaiting_approval"
            run.status = "awaiting_approval"
            run.updated_at = datetime.now()
            return
        if step.requires_approval and step.status != "approved":  # pre-approved by the caller
            step.approved_by = "auto"
            run.approvals.append({"step": step.name, "approved_by": "auto",
                                  "at": datetime.now().isoformat(timespec="seconds")})
        step.status = "running"
        if step.tool and dispatch is not None:
            ctx = dict(run.context)
            ctx.update(step.args or {})
            ctx.setdefault("objective", run.objective)
            ctx.setdefault("agent_key", run.agent_key)
            try:
                result = dispatch(step.tool, ctx)
                step.output = _summarise(result)
                step.status = "done"
            except Exception as exc:  # noqa: BLE001 - surface, never crash the run
                step.output = f"error: {exc}"
                step.status = "failed"
        else:
            step.status = "skipped"
            if not step.tool:
                step.output = step.capability
    run.status = "completed"
    run.completed_at = datetime.now()
    run.updated_at = run.completed_at
    done = [s for s in run.steps if s.status == "done"]
    run.metrics = {"steps": len(run.steps), "executed": len(done),
                   "failed": sum(1 for s in run.steps if s.status == "failed"),
                   "approvals": len(run.approvals)}


def approve_run(run_id: str, approver: str = "user",
                dispatch: Optional[Callable[[str, Dict[str, Any]], Any]] = None) -> Dict[str, Any]:
    run = next((r for r in runs_db if r.id == run_id), None)
    if not run:
        return {"error": f"Unknown run: {run_id}"}
    pending = [s for s in run.steps if s.status == "awaiting_approval"]
    if not pending:
        return {"error": "This run is not waiting for an approval", "status": run.status}
    for step in pending:
        step.status = "approved"
        step.approved_by = approver
        run.approvals.append({"step": step.name, "approved_by": approver,
                              "at": datetime.now().isoformat(timespec="seconds")})
    run.status = "running"
    if dispatch is not None:
        # Run the approved step's tool now; a later gate pauses again for its own approval.
        _execute(run, dispatch, approve=False)
        return run_view(run)
    for step in run.steps:
        if step.status == "approved":
            step.status = "skipped"
            step.output = step.output or "approved (not executed)"
    run.status = "completed"
    run.completed_at = datetime.now()
    run.updated_at = run.completed_at
    run.metrics = {"steps": len(run.steps),
                   "executed": sum(1 for s in run.steps if s.status == "done"),
                   "failed": sum(1 for s in run.steps if s.status == "failed"),
                   "approvals": len(run.approvals)}
    return run_view(run)


def list_runs(agent_key: Optional[str] = None, status: Optional[str] = None) -> List[AgentRun]:
    rows = runs_db
    if agent_key:
        rows = [r for r in rows if r.agent_key == agent_key]
    if status:
        rows = [r for r in rows if r.status == status]
    return rows


def get_run(run_id: str) -> Optional[AgentRun]:
    return next((r for r in runs_db if r.id == run_id), None)


def run_view(run: AgentRun) -> Dict[str, Any]:
    view = run.model_dump()
    agent = AGENTS_BY_KEY.get(run.agent_key, {})
    view["agent_name"] = agent.get("name")
    view["product"] = agent.get("product")
    view["step_count"] = len(run.steps)
    view["done_steps"] = sum(1 for s in run.steps if s.status == "done")
    view["awaiting_approval"] = [s.name for s in run.steps if s.status == "awaiting_approval"]
    return view


def orchestrate(objective: str, agent_keys: List[str]) -> Dict[str, Any]:
    """Plan a multi-agent hand-off chain for a shared objective."""
    keys = [k for k in agent_keys if k in AGENTS_BY_KEY][:AGENTIC_CONFIG["orchestration_max_agents"]]
    chain = []
    for i, k in enumerate(keys):
        a = AGENTS_BY_KEY[k]
        chain.append({"seq": i + 1, "agent": k, "name": a["name"],
                      "handoff_to": keys[i + 1] if i + 1 < len(keys) else None,
                      "tools": a["tools"]})
    return {"objective": objective, "agents": chain, "count": len(chain)}


# ============================================================
# Intent scoring models
# ============================================================


def _band(score: float, bands: List[tuple]) -> tuple:
    for threshold, label in bands:
        if score >= threshold:
            return threshold, label
    return 0, bands[-1][1]


def move_likelihood(features: Dict[str, Any]) -> Dict[str, Any]:
    """Score a contact's likelihood of moving (0–100) from lifecycle signals."""
    life = 0.0
    reasons: List[str] = []
    if features.get("job_change"):
        life += 0.5; reasons.append("recent job change")
    if features.get("new_baby"):
        life += 0.4; reasons.append("new baby / growing family")
    if features.get("empty_nest"):
        life += 0.6; reasons.append("empty nest — downsizing")
    if features.get("retirement"):
        life += 0.4; reasons.append("retirement")
    if features.get("divorce"):
        life += 0.5; reasons.append("life transition")
    life = min(1.0, life)

    tenure = float(features.get("tenure_years") or 0)
    tenure_score = min(1.0, tenure / 8.0) if features.get("owns") else min(1.0, tenure / 4.0)

    eng = max(0.0, min(1.0, float(features.get("engagement_score") or 0) / 100.0))
    fin = 1.0 if features.get("financial_ready") else 0.35
    market = max(0.0, min(1.0, float(features.get("market_heat") or 0.5)))
    days = float(features.get("days_since_contact") or 0)
    recency = max(0.0, 1.0 - days / 120.0)

    parts = {"life_event": life, "tenure": tenure_score, "engagement": eng,
             "financial_ready": fin, "market_signal": market, "recency": recency}
    score = sum(parts[k] * w for k, w in MOVE_LIKELIHOOD_WEIGHTS.items()) * 100
    score = round(score, 1)
    _, band = _band(score, [(70, "very_high"), (50, "high"), (30, "medium"), (0, "low")])
    if features.get("days_since_contact", 0) and days > 60:
        reasons.append(f"{int(days)} days since last contact")
    if not reasons:
        reasons.append("steady profile — nurture")
    action = {"very_high": "call today and offer a valuation",
              "high": "personal outreach this week",
              "medium": "add to drip campaign",
              "low": "keep on nurture list"}[band]
    return {"score": score, "band": band, "reasons": reasons,
            "components": {k: round(v, 3) for k, v in parts.items()},
            "recommended_action": action}


def seller_intent_score(features: Dict[str, Any]) -> Dict[str, Any]:
    """Score how likely a contact is to sell (0–100)."""
    reasons: List[str] = []
    equity = max(0.0, min(1.0, float(features.get("equity_pct") or 0) / 100.0))
    if equity >= 0.4:
        reasons.append(f"{round(equity * 100)}% equity")
    holding = min(1.0, float(features.get("holding_years") or 0) / 10.0)
    heat = max(0.0, min(1.0, float(features.get("market_heat") or 0.5)))
    if heat >= 0.7:
        reasons.append("hot seller's market")
    life = 0.8 if features.get("life_event") else 0.0
    if features.get("life_event"):
        reasons.append(str(features["life_event"]))
    fsbo = 1.0 if features.get("fsbo_signal") else 0.0
    if fsbo:
        reasons.append("selling privately / FSBO signal")
    eng = max(0.0, min(1.0, float(features.get("engagement_score") or 0) / 100.0))
    parts = {"equity": equity, "holding_time": holding, "market_heat": heat,
             "life_event": life, "fsbo_signal": fsbo, "engagement": eng}
    score = round(sum(parts[k] * w for k, w in SELLER_INTENT_WEIGHTS.items()) * 100, 1)
    _, band = _band(score, [(70, "ready"), (45, "warming"), (25, "curious"), (0, "cold")])
    if not reasons:
        reasons.append("no active signals")
    return {"score": score, "band": band, "reasons": reasons,
            "components": {k: round(v, 3) for k, v in parts.items()},
            "recommended_action": {"ready": "book a listing appointment",
                                   "warming": "send a CMA by e-mail",
                                   "curious": "nurture with market updates",
                                   "cold": "keep on the mailing list"}[band]}


def prioritise_actions(signals: List[Dict[str, Any]], limit: int = 20) -> Dict[str, Any]:
    """Rank inbound signals into a human-in-the-loop action list ("Smart Actions").

    Each signal: ``{kind, title, entity_type, entity_id, due_in_hours, impact (1-5),
    urgency (1-5), reason, suggested_agent}``.
    """
    rows: List[Dict[str, Any]] = []
    for s in signals:
        impact = float(s.get("impact") or 3)
        urgency = float(s.get("urgency") or 3)
        due = s.get("due_in_hours")
        # overdue items escalate; distant items decay
        if due is None:
            decay = 0.0
        elif due <= 0:
            decay = 2.5
        else:
            decay = max(-2.0, 1.5 - due / 24.0)
        priority = round(impact * 2.0 + urgency * 2.0 + decay, 2)
        if priority >= 16 or (due is not None and due <= 0):
            band = "urgent"
        elif priority >= 12:
            band = "high"
        else:
            band = "normal"
        rows.append({
            "kind": s.get("kind"), "title": s.get("title"),
            "entity_type": s.get("entity_type"), "entity_id": s.get("entity_id"),
            "due_in_hours": due, "impact": impact, "urgency": urgency,
            "priority": priority, "band": band, "reason": s.get("reason"),
            "suggested_agent": s.get("suggested_agent"),
            "sla_hours": AGENTIC_CONFIG["smart_action_sla_hours"][band],
        })
    rows.sort(key=lambda r: r["priority"], reverse=True)
    rows = rows[:limit]
    return {"count": len(rows), "by_band": {
        b: sum(1 for r in rows if r["band"] == b) for b in ("urgent", "high", "normal")},
        "actions": rows}
