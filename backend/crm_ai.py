"""
The CRM's intelligence: dashboard analytics, lead briefs, message drafting, voice / text notes,
a question-answering copilot and inbound lead capture.

Every feature works without AI credit (rules and templates). When a chat model is configured —
OpenAI (``OPENAI_API_KEY``, ``OPENAI_MODEL``) or any OpenAI-compatible server such as LM Studio
(``LLM_BASE_URL``, ``LLM_MODEL``) — it writes the summaries, drafts and answers instead, and the
response says ``source: "ai"``; otherwise ``source: "rules"``.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import httpx

import crm_channels
import server as core
from openai_facade import UPSTREAM_API_KEY, UPSTREAM_BASE_URL, UPSTREAM_MODEL, UPSTREAM_PROVIDER

CLOSED_LEAD = ("won", "lost")
OPEN_DEAL = lambda d: d.stage not in ("closed_won", "closed_lost")  # noqa: E731


# ============================================================ LLM


def ai_available() -> bool:
    return bool(UPSTREAM_BASE_URL)


def llm_json(system: str, user: str, max_tokens: int = 900) -> Optional[Dict[str, Any]]:
    """Ask the configured chat model for a JSON object; None when not configured or on any error."""
    if not UPSTREAM_BASE_URL:
        return None
    body: Dict[str, Any] = {
        "model": UPSTREAM_MODEL,
        "messages": [{"role": "system", "content": system + "\nReply with one JSON object only."},
                     {"role": "user", "content": user}],
    }
    if UPSTREAM_PROVIDER == "openai":
        body["response_format"] = {"type": "json_object"}
        body["max_completion_tokens"] = max_tokens
    else:
        body["max_tokens"] = max_tokens
        body["temperature"] = 0.4
    headers = {"Content-Type": "application/json"}
    if UPSTREAM_API_KEY:
        headers["Authorization"] = f"Bearer {UPSTREAM_API_KEY}"
    try:
        r = httpx.post(f"{UPSTREAM_BASE_URL}/chat/completions", json=body, headers=headers, timeout=60)
        if r.status_code >= 400:
            return None
        text = r.json()["choices"][0]["message"]["content"] or ""
        m = re.search(r"\{.*\}", text, re.S)
        return json.loads(m.group(0)) if m else None
    except (httpx.HTTPError, ValueError, KeyError, IndexError):
        return None


# ============================================================ helpers


def pkr(v: Optional[float]) -> str:
    if v is None:
        return "—"
    if v == 0:
        return "PKR 0"
    if v >= 1e7:
        return f"PKR {v / 1e7:.2f} crore"
    if v >= 1e5:
        return f"PKR {v / 1e5:.1f} lakh"
    return f"PKR {v:,.0f}"


def _dt(v: Any) -> Optional[datetime]:
    if isinstance(v, datetime):
        return v.replace(tzinfo=None)
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day)
    if isinstance(v, str) and v:
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None
    return None


def _city(city_id: Optional[str]) -> Optional[str]:
    c = next((c for c in core.cities_db if c.id == city_id), None) if city_id else None
    return c.name if c else None


def _agent(agent_id: Optional[str]) -> Optional[Any]:
    return next((a for a in core.agents_db if a.id == agent_id), None) if agent_id else None


def _lead(lead_id: str) -> Optional[Any]:
    return next((x for x in core.leads_db if x.id == lead_id), None)


def _touches(entity_ids: List[str]) -> List[Any]:
    ids = set(entity_ids)
    return sorted((i for i in core.interactions_db if i.entity_id in ids), key=lambda i: _dt(i.occurred_at) or datetime.min)


def _last_touch(entity_ids: List[str]) -> Optional[datetime]:
    t = _touches(entity_ids)
    return _dt(t[-1].occurred_at) if t else None


def _days(since: Optional[datetime], now: Optional[datetime] = None) -> Optional[int]:
    return None if since is None else max(0, ((now or datetime.now()) - since).days)


def temperature(score: int) -> str:
    return "hot" if score >= 70 else "warm" if score >= 45 else "cold"


def next_action(lead: Any, last_contact_days: Optional[int]) -> Dict[str, str]:
    """Rules-based next best action for a lead: what, which channel, how urgent."""
    has_phone = bool(lead.phone)
    if lead.status in CLOSED_LEAD:
        return {"action": "Closed — ask for a referral or review" if lead.status == "won" else "Closed — re-engage in 90 days with new matches",
                "channel": "whatsapp" if has_phone else "email", "urgency": "low"}
    if last_contact_days is None:
        return {"action": "First contact: call within the hour, then send matching listings on WhatsApp",
                "channel": "call" if has_phone else "email", "urgency": "urgent"}
    if last_contact_days >= 14:
        return {"action": f"Gone quiet for {last_contact_days} days: re-engage with fresh matches and a price update",
                "channel": "whatsapp" if has_phone else "email", "urgency": "high"}
    stage = {
        "new": ("Qualify budget, timeline and financing on a call", "call", "high"),
        "contacted": ("Share 3 matching listings and propose a site visit", "whatsapp", "high"),
        "qualified": ("Book a site visit this week", "call", "high"),
        "proposal": ("Follow up on the proposal and payment plan within 2 days", "whatsapp", "medium"),
        "negotiation": ("Close: confirm the token amount and booking date", "call", "urgent"),
    }.get(lead.status, ("Follow up", "whatsapp", "medium"))
    channel = stage[1] if has_phone else "email"
    return {"action": stage[0], "channel": channel, "urgency": stage[2]}


# ============================================================ analytics


def insights(days: int = 30, agent_id: Optional[str] = None) -> Dict[str, Any]:
    """Everything the CRM dashboard shows, for the last ``days`` days (optionally one agent's book)."""
    now = datetime.now()
    since = now - timedelta(days=days)
    today = now.date()
    leads = [x for x in core.leads_db if not agent_id or x.assigned_agent_id == agent_id]
    deals = [d for d in core.deals_db if not agent_id or d.agent_id == agent_id]
    tasks = [t for t in core.tasks_db if not agent_id or t.assigned_agent_id == agent_id]
    appts = [a for a in core.appointments_db if not agent_id or a.agent_id == agent_id]
    inter = [i for i in core.interactions_db if not agent_id or i.agent_id == agent_id]

    touches: Dict[str, List[datetime]] = defaultdict(list)
    for i in core.interactions_db:
        if (t := _dt(i.occurred_at)):
            touches[i.entity_id].append(t)

    def last_contact(lead: Any) -> Optional[datetime]:
        ts = touches.get(lead.id, [])
        if lead.converted_customer_id:
            ts = ts + touches.get(lead.converted_customer_id, [])
        return max(ts) if ts else None

    open_leads = [x for x in leads if x.status not in CLOSED_LEAD]
    won = [x for x in leads if x.status == "won"]
    lost = [x for x in leads if x.status == "lost"]
    new_leads = [x for x in leads if (_dt(x.created_at) or now) >= since]
    open_deals = [d for d in deals if OPEN_DEAL(d)]
    won_deals = [d for d in deals if d.stage == "closed_won"]

    def due(t: Any) -> Optional[date]:
        d = _dt(t.due_date)
        return d.date() if d else None

    open_tasks = [t for t in tasks if t.status in ("open", "in_progress")]
    overdue = [t for t in open_tasks if (d := due(t)) and d < today]
    due_today = [t for t in open_tasks if due(t) == today]
    upcoming = sorted((a for a in appts if a.status == "scheduled" and (s := _dt(a.scheduled_at)) and now - timedelta(hours=2) <= s <= now + timedelta(days=7)),
                      key=lambda a: _dt(a.scheduled_at))

    response_hours = []
    for x in leads:
        ts = sorted(touches.get(x.id, []))
        if ts and (c := _dt(x.created_at)):
            response_hours.append(max(0.0, (ts[0] - c).total_seconds() / 3600))
    uncontacted = [x for x in open_leads if not touches.get(x.id)]

    kpis = {
        "leads_total": len(leads),
        "leads_new": len(new_leads),
        "leads_open": len(open_leads),
        "leads_hot": sum(1 for x in open_leads if x.score >= 70),
        "leads_uncontacted": len(uncontacted),
        "conversion_rate": round(len(won) / (len(won) + len(lost)), 3) if (won or lost) else None,
        "avg_first_response_hours": round(sum(response_hours) / len(response_hours), 1) if response_hours else None,
        "pipeline_open": round(sum(d.amount for d in open_deals)),
        "pipeline_weighted": round(sum(d.amount * d.probability / 100 for d in open_deals)),
        "won_value": round(sum(d.amount for d in won_deals)),
        "won_count": len(won_deals),
        "avg_deal_size": round(sum(d.amount for d in won_deals) / len(won_deals)) if won_deals else None,
        "commission_won": round(sum(d.commission for d in won_deals)),
        "tasks_open": len(open_tasks),
        "tasks_overdue": len(overdue),
        "tasks_due_today": len(due_today),
        "appointments_week": len(upcoming),
        "interactions_period": sum(1 for i in inter if (_dt(i.occurred_at) or now) >= since),
    }

    # Daily trend.
    day_keys = [(since + timedelta(days=k)).date() for k in range(days + 1)]
    trend = {d: {"date": d.isoformat(), "leads": 0, "touches": 0, "won": 0} for d in day_keys}
    for x in leads:
        if (c := _dt(x.created_at)) and c.date() in trend:
            trend[c.date()]["leads"] += 1
    for i in inter:
        if (o := _dt(i.occurred_at)) and o.date() in trend:
            trend[o.date()]["touches"] += 1
    for d in won_deals:
        if (u := _dt(d.updated_at)) and u.date() in trend:
            trend[u.date()]["won"] += round(d.amount)

    by_status = [{"status": s, "count": sum(1 for x in leads if x.status == s)} for s in core.LEAD_STATUSES]
    reached = []
    order = ["new", "contacted", "qualified", "proposal", "negotiation", "won"]
    for k, s in enumerate(order):
        reached.append({"stage": s, "count": sum(1 for x in leads if x.status in order[k:])})
    pipeline = [{"stage": s, "count": sum(1 for d in deals if d.stage == s),
                 "value": round(sum(d.amount for d in deals if d.stage == s))} for s in core.DEAL_STAGES]

    # Agent leaderboard.
    board = []
    for a in core.agents_db:
        if agent_id and a.id != agent_id:
            continue
        al = [x for x in core.leads_db if x.assigned_agent_id == a.id]
        ad = [d for d in core.deals_db if d.agent_id == a.id]
        aw = [d for d in ad if d.stage == "closed_won"]
        contacted = sum(1 for x in al if touches.get(x.id))
        board.append({
            "agent_id": a.id, "name": a.name, "active": a.active, "rating": a.rating,
            "leads": len(al), "contacted_pct": round(100 * contacted / len(al)) if al else None,
            "hot": sum(1 for x in al if x.score >= 70 and x.status not in CLOSED_LEAD),
            "won_count": len(aw), "won_value": round(sum(d.amount for d in aw)),
            "pipeline": round(sum(d.amount for d in ad if OPEN_DEAL(d))),
            "commission": round(sum(d.commission for d in aw)),
            "overdue_tasks": sum(1 for t in core.tasks_db if t.assigned_agent_id == a.id and t.status in ("open", "in_progress") and (dd := due(t)) and dd < today),
        })
    board.sort(key=lambda r: (-r["won_value"], -r["pipeline"], -r["leads"]))

    # Who to call now: score, plus urgency for silence and for never-contacted leads.
    hot = []
    for x in open_leads:
        lc = last_contact(x)
        d = _days(lc, now)
        prio = x.score + (25 if d is None else min(20, d)) + (10 if x.status in ("negotiation", "proposal") else 0)
        na = next_action(x, d)
        hot.append({"id": x.id, "name": x.name, "phone": x.phone, "email": x.email, "status": x.status, "score": x.score,
                    "temperature": temperature(x.score), "city": _city(x.city_id), "budget_max": x.budget_max,
                    "agent": getattr(_agent(x.assigned_agent_id), "name", None), "last_contact_days": d,
                    "priority": prio, **na})
    hot.sort(key=lambda r: -r["priority"])

    at_risk = []
    for dl in open_deals:
        ids = [dl.id] + [v for v in (dl.lead_id, dl.customer_id) if v]
        d = _days(_last_touch(ids), now)
        close = _dt(dl.expected_close_date)
        reasons = []
        if d is None or d >= 14:
            reasons.append("no contact yet" if d is None else f"no contact for {d} days")
        if close and close.date() < today:
            reasons.append(f"close date passed ({close.date().isoformat()})")
        if reasons:
            at_risk.append({"id": dl.id, "title": dl.title, "stage": dl.stage, "amount": dl.amount, "probability": dl.probability,
                            "agent": getattr(_agent(dl.agent_id), "name", None), "reasons": reasons})
    at_risk.sort(key=lambda r: -r["amount"])

    def task_row(t: Any) -> Dict[str, Any]:
        return {"id": t.id, "title": t.title, "due_date": t.due_date, "priority": t.priority, "status": t.status,
                "related_type": t.related_type, "related_id": t.related_id, "agent": getattr(_agent(t.assigned_agent_id), "name", None),
                "overdue": bool((d := due(t)) and d < today)}

    return {
        "period_days": days, "generated_at": now.isoformat(timespec="seconds"), "ai": ai_available(),
        "kpis": kpis,
        "trend": list(trend.values()),
        "by_source": [{"source": k, "count": v} for k, v in Counter(x.source or "unknown" for x in leads).most_common()],
        "by_status": by_status,
        "by_city": [{"city": k, "count": v} for k, v in Counter(_city(x.city_id) or "Unknown" for x in leads).most_common(8)],
        "channel_mix": [{"channel": k, "count": v} for k, v in Counter(i.channel for i in inter if (_dt(i.occurred_at) or now) >= since).most_common()],
        "funnel": reached,
        "pipeline": pipeline,
        "agents": board,
        "priority_leads": hot[:10],
        "at_risk_deals": at_risk[:8],
        "agenda": {
            "overdue": [task_row(t) for t in sorted(overdue, key=lambda t: t.due_date or "")[:10]],
            "today": [task_row(t) for t in due_today[:10]],
            "appointments": [{"id": a.id, "title": a.title, "scheduled_at": a.scheduled_at, "agent": getattr(_agent(a.agent_id), "name", None),
                              "lead_id": a.lead_id, "property_id": a.property_id} for a in upcoming[:10]],
        },
        "channels": crm_channels.status(),
    }


# ============================================================ lead brief & drafts

GOALS = {
    "follow_up": "a friendly follow-up",
    "new_matches": "sharing new matching properties",
    "site_visit": "inviting them to a site visit",
    "price_update": "a price or payment-plan update",
    "re_engage": "re-engaging a lead who went quiet",
    "thank_you": "thanking them after a visit or meeting",
    "proposal": "sending a proposal / payment plan",
}


def _template(name: str, goal: str, lang: str, matches: List[Dict[str, Any]], agent: Optional[str], city: Optional[str]) -> Dict[str, str]:
    first = (name or "").split()[0] if name else ""
    top = matches[0] if matches else None
    sig = agent or "Watan-e-Pak team"
    if lang == "ur":
        lines = {
            "follow_up": f"السلام علیکم {first}! امید ہے آپ خیریت سے ہیں۔ آپ کی پراپرٹی کی تلاش کے بارے میں رابطہ کر رہا ہوں — کیا ہم آج مختصر بات کر سکتے ہیں؟",
            "new_matches": f"السلام علیکم {first}! آپ کے بجٹ کے مطابق {city or 'آپ کے علاقے'} میں نئی پراپرٹیز آئی ہیں" + (f"، جیسے «{top['title']}»" if top else "") + "۔ تفصیل بھیج دوں؟",
            "site_visit": f"السلام علیکم {first}! کیا اس ہفتے سائٹ وزٹ کے لیے وقت ہے؟ میں آپ کے لیے وزٹ ترتیب دے دیتا ہوں۔",
            "price_update": f"السلام علیکم {first}! جس پراپرٹی میں آپ کی دلچسپی تھی اس کی قیمت / قسطوں کے پلان میں نئی آفر آئی ہے۔ تفصیل بھیجوں؟",
            "re_engage": f"السلام علیکم {first}! کافی دن ہو گئے — کیا آپ اب بھی پراپرٹی دیکھ رہے ہیں؟ مارکیٹ میں کچھ اچھی آفرز ہیں۔",
            "thank_you": f"شکریہ {first} آج وقت دینے کا! کوئی سوال ہو تو بلا جھجک بتائیں۔",
            "proposal": f"السلام علیکم {first}! آپ کے لیے قیمت اور ادائیگی کا پلان تیار ہے۔ کیا میں ابھی بھیج دوں؟",
        }
        body = lines.get(goal, lines["follow_up"]) + f"\n— {sig}"
        return {"subject": "Watan-e-Pak — آپ کی پراپرٹی کی تلاش", "body": body}
    lines = {
        "follow_up": f"Hi {first}, hope you're well! Following up on your property search — do you have 5 minutes for a quick call today?",
        "new_matches": f"Hi {first}, new listings just came in{f' in {city}' if city else ''} that fit your budget" + (f", including \"{top['title']}\"" if top else "") + ". Shall I send you the details?",
        "site_visit": f"Hi {first}, would you like to see the property in person this week? I can arrange a site visit at a time that suits you.",
        "price_update": f"Hi {first}, there's a new price / payment-plan offer on the property you liked. Want me to share the details?",
        "re_engage": f"Hi {first}, it's been a while — are you still looking? The market has some good offers right now and I'd be happy to help.",
        "thank_you": f"Thank you for your time today, {first}! Let me know if any questions come up.",
        "proposal": f"Hi {first}, your price breakdown and payment plan are ready. Shall I send them over?",
    }
    return {"subject": "Your property search — Watan-e-Pak", "body": lines.get(goal, lines["follow_up"]) + f"\n— {sig}"}


def _lead_context(lead: Any) -> Dict[str, Any]:
    found = core._match_properties_for_lead(lead, limit=5)
    matches = [{"id": p.get("id"), "title": p.get("title"), "price": p.get("price")} for p in found.get("properties", [])]
    ids = [lead.id] + ([lead.converted_customer_id] if lead.converted_customer_id else [])
    touches = _touches(ids)
    return {
        "lead": {"name": lead.name, "status": lead.status, "score": lead.score, "source": lead.source, "phone": bool(lead.phone),
                 "email": bool(lead.email), "interest": " ".join(filter(None, [lead.interest_use_type, lead.interest_category])) or None,
                 "budget": f"{pkr(lead.budget_min)} – {pkr(lead.budget_max)}" if (lead.budget_min or lead.budget_max) else None,
                 "city": _city(lead.city_id), "notes": lead.notes, "created": str(lead.created_at)[:10]},
        "agent": getattr(_agent(lead.assigned_agent_id), "name", None),
        "timeline": [{"when": str(i.occurred_at)[:16], "channel": i.channel, "direction": i.direction, "summary": i.summary} for i in touches[-10:]],
        "matches": matches,
        "last_contact_days": _days(_dt(touches[-1].occurred_at)) if touches else None,
    }


def lead_brief(lead_id: str, lang: str = "en") -> Dict[str, Any]:
    lead = _lead(lead_id)
    if not lead:
        return {"error": "Lead not found"}
    ctx = _lead_context(lead)
    d = ctx["last_contact_days"]
    na = next_action(lead, d)
    goal = "re_engage" if (d or 0) >= 14 else {"new": "follow_up", "contacted": "new_matches", "qualified": "site_visit",
                                               "proposal": "proposal", "negotiation": "price_update"}.get(lead.status, "follow_up")
    tpl = _template(lead.name, goal, lang, ctx["matches"], ctx["agent"], ctx["lead"]["city"])
    talking = []
    if ctx["lead"]["budget"]:
        talking.append(f"Budget {ctx['lead']['budget']}")
    if ctx["matches"]:
        talking.append(f"{len(ctx['matches'])} matching listings, e.g. {ctx['matches'][0]['title']}")
    if ctx["lead"]["interest"]:
        talking.append(f"Interested in {ctx['lead']['interest']}")
    if lead.source:
        talking.append(f"Came from {lead.source}")
    risks = []
    if d is None:
        risks.append("Not contacted yet — response speed decides most portal leads")
    elif d >= 14:
        risks.append(f"No contact for {d} days")
    if not lead.phone:
        risks.append("No phone number — e-mail only")
    if not (lead.budget_min or lead.budget_max):
        risks.append("Budget unknown — qualify it on the next call")
    follow_days = {"urgent": 0, "high": 1, "medium": 2, "low": 7}[na["urgency"]]
    out: Dict[str, Any] = {
        "lead_id": lead.id, "name": lead.name, "source": "rules", "lang": lang,
        "temperature": temperature(lead.score), "score": lead.score,
        "summary": f"{lead.name} is a {temperature(lead.score)} {lead.status} lead (score {lead.score})"
                   + (f" looking for {ctx['lead']['interest']}" if ctx["lead"]["interest"] else "")
                   + (f" in {ctx['lead']['city']}" if ctx["lead"]["city"] else "")
                   + (f", budget {ctx['lead']['budget']}" if ctx["lead"]["budget"] else "")
                   + (". Never contacted." if d is None else f". Last contact {d} day{'s' if d != 1 else ''} ago."),
        "next_best_action": na["action"], "channel": na["channel"], "urgency": na["urgency"],
        "follow_up_date": (date.today() + timedelta(days=follow_days)).isoformat(),
        "talking_points": talking, "risks": risks,
        "drafts": {"whatsapp": tpl["body"], "sms": tpl["body"][:300], "email_subject": tpl["subject"], "email_body": tpl["body"]},
        "goal": goal, "matches": ctx["matches"],
    }
    ai = llm_json(
        "You are a senior real-estate sales coach in Pakistan advising an agent on one lead. Be specific, practical and brief. "
        "Money in PKR lakh/crore. Messages must be warm, short, WhatsApp-friendly, no emojis overload, and signed by the agent. "
        + ("Write summary, actions and all drafts in Urdu (Urdu script)." if lang == "ur" else "Write in English."),
        "Lead context (JSON):\n" + json.dumps(ctx, ensure_ascii=False, default=str)
        + "\nReturn JSON with keys: summary (2 sentences), temperature (hot|warm|cold), next_best_action, channel (call|whatsapp|email|sms|site_visit), "
          "urgency (urgent|high|medium|low), follow_up_in_days (int), talking_points (list of 3-5), risks (list), "
          "drafts {whatsapp, sms (<=300 chars), email_subject, email_body}.",
    )
    if ai:
        out["source"] = "ai"
        for k in ("summary", "temperature", "next_best_action", "channel", "urgency", "talking_points", "risks"):
            if ai.get(k):
                out[k] = ai[k]
        if isinstance(ai.get("follow_up_in_days"), (int, float)):
            out["follow_up_date"] = (date.today() + timedelta(days=int(ai["follow_up_in_days"]))).isoformat()
        if isinstance(ai.get("drafts"), dict):
            out["drafts"].update({k: v for k, v in ai["drafts"].items() if isinstance(v, str) and v.strip()})
    return out


def _entity(entity_type: str, entity_id: str) -> Tuple[Optional[Any], Optional[str]]:
    """(record, error) for a lead or customer."""
    if entity_type == "lead":
        x = _lead(entity_id)
    elif entity_type == "customer":
        x = next((c for c in core.customers_db if c.id == entity_id), None)
    else:
        return None, "entity_type must be lead or customer"
    return (x, None) if x else (None, f"{entity_type.title()} not found")


def draft_message(entity_type: str, entity_id: str, channel: str = "whatsapp", goal: str = "follow_up",
                  lang: str = "en", tone: str = "friendly", notes: Optional[str] = None) -> Dict[str, Any]:
    x, err = _entity(entity_type, entity_id)
    if err:
        return {"error": err}
    agent = getattr(_agent(getattr(x, "assigned_agent_id", None)), "name", None)
    ctx = _lead_context(x) if entity_type == "lead" else {"customer": {"name": x.name, "type": x.type, "city": _city(x.city_id), "notes": x.notes},
                                                          "agent": agent, "matches": [], "timeline": [
                                                              {"when": str(i.occurred_at)[:16], "channel": i.channel, "summary": i.summary} for i in _touches([x.id])[-8:]]}
    tpl = _template(x.name, goal, lang, ctx.get("matches", []), agent, _city(getattr(x, "city_id", None)))
    out = {"channel": channel, "goal": goal, "lang": lang, "subject": tpl["subject"] if channel == "email" else None,
           "body": tpl["body"][:300] if channel == "sms" else tpl["body"], "source": "rules"}
    ai = llm_json(
        "You write outreach messages for a Pakistani real-estate agent. Short, personal, specific, honest; no fake urgency. "
        f"Tone: {tone}. Channel: {channel} ({'max 300 characters' if channel == 'sms' else 'WhatsApp-friendly, under 90 words' if channel == 'whatsapp' else 'email with a subject'}). "
        + ("Write in Urdu (Urdu script)." if lang == "ur" else "Write in English.")
        + f" Sign as {agent or 'the Watan-e-Pak team'}.",
        f"Goal: {GOALS.get(goal, goal)}.\nExtra instructions: {notes or '-'}\nContext (JSON):\n" + json.dumps(ctx, ensure_ascii=False, default=str)
        + '\nReturn JSON: {"subject": string or null, "body": string}.',
        max_tokens=500,
    )
    if ai and ai.get("body"):
        out.update({"body": ai["body"], "subject": ai.get("subject") or out["subject"], "source": "ai"})
    return out


# ============================================================ voice / text notes

_MONEY = re.compile(r"(\d+(?:\.\d+)?)\s*(crore|cr|lakh|lac|lakhs|million|m)\b", re.I)


def _rules_note(text: str) -> Dict[str, Any]:
    low = text.lower()
    budget = None
    for m in _MONEY.finditer(text):
        n = float(m.group(1))
        unit = m.group(2).lower()
        v = n * (1e7 if unit in ("crore", "cr") else 1e5 if unit.startswith("la") else 1e6)
        budget = max(budget or 0, v)
    follow = None
    if any(w in low for w in ("tomorrow", "kal ", "کل")):
        follow = (date.today() + timedelta(days=1)).isoformat()
    elif "next week" in low or "agle hafte" in low:
        follow = (date.today() + timedelta(days=7)).isoformat()
    elif "today" in low or "aaj" in low:
        follow = date.today().isoformat()
    status = None
    if any(w in low for w in ("not interested", "no longer", "bought elsewhere")):
        status = "lost"
    elif any(w in low for w in ("token", "booking", "negotiat", "offer", "discount")):
        status = "negotiation"
    elif any(w in low for w in ("visit", "site", "show the property", "viewing")):
        status = "qualified"
    sentiment = "negative" if any(w in low for w in ("angry", "unhappy", "not interested", "expensive", "too high")) else \
        "positive" if any(w in low for w in ("interested", "liked", "happy", "keen", "ready")) else "neutral"
    tasks = []
    if follow:
        tasks.append({"title": "Follow up" + (" — site visit" if status == "qualified" else ""), "due_date": follow, "priority": "high"})
    return {"summary": text.strip()[:400], "sentiment": sentiment, "budget_pkr": budget, "follow_up_date": follow,
            "status_suggestion": status, "next_step": tasks[0]["title"] if tasks else None, "tasks": tasks}


def analyse_note(text: str, entity_type: Optional[str] = None, entity_id: Optional[str] = None) -> Dict[str, Any]:
    out = {**_rules_note(text), "source": "rules"}
    ctx = None
    if entity_type and entity_id:
        x, _ = _entity(entity_type, entity_id)
        if x:
            ctx = {"name": x.name, "status": getattr(x, "status", None), "type": getattr(x, "type", None)}
    ai = llm_json(
        "You turn an estate agent's spoken or typed note about a client into CRM data. The note may be in English, Urdu or Roman Urdu. "
        f"Today is {date.today().isoformat()}. Money in PKR (1 lakh = 100,000; 1 crore = 10,000,000).",
        f"Client: {json.dumps(ctx, ensure_ascii=False) if ctx else 'unknown'}\nNote:\n{text}\n"
        "Return JSON: summary (one or two English sentences), sentiment (positive|neutral|negative), intent, budget_pkr (number or null), "
        "timeline, next_step, follow_up_date (YYYY-MM-DD or null), status_suggestion (new|contacted|qualified|proposal|negotiation|won|lost or null), "
        "tasks (list of {title, due_date YYYY-MM-DD or null, priority low|medium|high|urgent}).",
        max_tokens=600,
    )
    if ai:
        out["source"] = "ai"
        for k in ("summary", "sentiment", "intent", "budget_pkr", "timeline", "next_step", "follow_up_date", "status_suggestion", "tasks"):
            if ai.get(k) not in (None, "", []):
                out[k] = ai[k]
    return out


def apply_note(analysis: Dict[str, Any], transcript: str, entity_type: str, entity_id: str,
               agent_id: Optional[str], channel: str = "voice_note") -> Dict[str, Any]:
    """Log the note on the timeline, create its follow-up tasks, fill an unknown budget."""
    x, err = _entity(entity_type, entity_id)
    if err:
        return {"error": err}
    agent_id = agent_id or getattr(x, "assigned_agent_id", None)
    summary = analysis.get("summary") or transcript[:400]
    inter = json.loads(core.crm_log_interaction(entity_type=entity_type, entity_id=entity_id, summary=summary,
                                                channel=channel, direction="internal", agent_id=agent_id))
    created = []
    for t in (analysis.get("tasks") or [])[:5]:
        if not isinstance(t, dict) or not t.get("title"):
            continue
        pr = t.get("priority") if t.get("priority") in core.TASK_PRIORITIES else "medium"
        created.append(json.loads(core.crm_add_task(title=str(t["title"])[:120], description=summary, assigned_agent_id=agent_id,
                                                    related_type=entity_type, related_id=entity_id, due_date=t.get("due_date"), priority=pr)))
    updated = {}
    if entity_type == "lead" and isinstance(analysis.get("budget_pkr"), (int, float)) and analysis["budget_pkr"] > 0 and not x.budget_max:
        x.budget_max = float(analysis["budget_pkr"])
        x.updated_at = datetime.now()
        updated["budget_max"] = x.budget_max
    return {"interaction": inter, "tasks": created, "updated": updated}


# ============================================================ copilot


def _snapshot(agent_id: Optional[str] = None) -> Dict[str, Any]:
    ins = insights(30, agent_id)
    leads = [{"id": x.id, "name": x.name, "status": x.status, "score": x.score, "source": x.source, "city": _city(x.city_id),
              "budget_max": x.budget_max, "agent": getattr(_agent(x.assigned_agent_id), "name", None)}
             for x in core.leads_db if not agent_id or x.assigned_agent_id == agent_id][:80]
    return {"kpis": ins["kpis"], "priority_leads": ins["priority_leads"][:8], "at_risk_deals": ins["at_risk_deals"][:5],
            "agenda": ins["agenda"], "agents": ins["agents"], "pipeline": ins["pipeline"], "leads": leads}


def ask(question: str, lang: str = "en", agent_id: Optional[str] = None) -> Dict[str, Any]:
    """Answer from CRM data; ``agent_id`` limits it to one agent's book."""
    q = question.strip()
    if not q:
        return {"error": "Ask a question"}
    snap = _snapshot(agent_id)
    ai = llm_json(
        "You are the CRM copilot of a Pakistani real-estate portal, talking to a sales agent or manager. Answer from the CRM data given — "
        "never invent leads or numbers. Be brief and actionable (bullets welcome). Money in PKR lakh/crore. "
        + ("Answer in Urdu (Urdu script)." if lang == "ur" else "Answer in the user's language (English, Urdu or Roman Urdu)."),
        f"CRM data (JSON):\n{json.dumps(snap, ensure_ascii=False, default=str)}\n\nQuestion: {q}\n"
        'Return JSON: {"answer": markdown string, "lead_ids": [ids of leads you refer to]}',
        max_tokens=700,
    )
    if ai and ai.get("answer"):
        return {"answer": ai["answer"], "lead_ids": ai.get("lead_ids") or [], "source": "ai"}
    return {**_rules_answer(q.lower(), snap), "source": "rules"}


def _rules_answer(q: str, s: Dict[str, Any]) -> Dict[str, Any]:
    k = s["kpis"]
    if any(w in q for w in ("hot", "call", "priority", "today", "who should")):
        rows = s["priority_leads"][:5]
        lines = [f"- **{r['name']}** ({r['status']}, score {r['score']}) — {r['action']}" for r in rows]
        return {"answer": "Call these first:\n" + "\n".join(lines) if rows else "No open leads right now.", "lead_ids": [r["id"] for r in rows]}
    if any(w in q for w in ("overdue", "task", "pending")):
        rows = s["agenda"]["overdue"] + s["agenda"]["today"]
        return {"answer": f"{k['tasks_overdue']} overdue and {k['tasks_due_today']} due today:\n"
                + "\n".join(f"- {t['title']} ({t['due_date'] or 'no date'}, {t['agent'] or 'unassigned'})" for t in rows[:8]), "lead_ids": []}
    if any(w in q for w in ("risk", "stuck", "slipping", "silent")):
        rows = s["at_risk_deals"]
        if not rows:
            return {"answer": "No deals are at risk — every open deal has recent contact and a future close date.", "lead_ids": []}
        lines = [f"- **{d['title']}** ({pkr(d['amount'])}, {d['stage']}) — {'; '.join(d['reasons'])}" for d in rows]
        return {"answer": f"{len(rows)} deal{'s' if len(rows) > 1 else ''} at risk:\n" + "\n".join(lines), "lead_ids": []}
    if any(w in q for w in ("pipeline", "revenue", "forecast", "deal")):
        return {"answer": f"Open pipeline {pkr(k['pipeline_open'])}, weighted {pkr(k['pipeline_weighted'])}. Won {k['won_count']} deals worth {pkr(k['won_value'])}."
                + (f" {len(s['at_risk_deals'])} deals are at risk." if s["at_risk_deals"] else ""), "lead_ids": []}
    if any(w in q for w in ("agent", "best", "top", "leaderboard")):
        rows = s["agents"][:5]
        return {"answer": "Agent leaderboard:\n" + "\n".join(f"- {a['name']}: {a['won_count']} won ({pkr(a['won_value'])}), pipeline {pkr(a['pipeline'])}, {a['leads']} leads" for a in rows), "lead_ids": []}
    for city in {r["city"] for r in s["leads"] if r["city"]}:
        if city.lower() in q:
            rows = [r for r in s["leads"] if r["city"] == city]
            return {"answer": f"{len(rows)} leads in {city}:\n" + "\n".join(f"- {r['name']} ({r['status']}, score {r['score']})" for r in rows[:10]),
                    "lead_ids": [r["id"] for r in rows[:10]]}
    return {"answer": f"{k['leads_open']} open leads ({k['leads_hot']} hot, {k['leads_uncontacted']} not contacted yet), "
                      f"open pipeline {pkr(k['pipeline_open'])}, {k['tasks_overdue']} overdue tasks. "
                      "Ask me about hot leads, overdue tasks, the pipeline, agents or a city.", "lead_ids": []}


# ============================================================ inbound leads


def _pick_agent(city_id: Optional[str]) -> Optional[str]:
    """Route to an active agent in the lead's region, else the one with the fewest open leads."""
    active = [a for a in core.agents_db if a.active]
    if not active:
        return None
    city = (_city(city_id) or "").lower()
    regional = [a for a in active if city and a.region and city in a.region.lower()]
    pool = regional or active
    load = Counter(x.assigned_agent_id for x in core.leads_db if x.status not in CLOSED_LEAD)
    return min(pool, key=lambda a: (load.get(a.id, 0), -a.rating)).id


def _flatten(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten Facebook / Instagram lead-ad ``field_data`` and nested form payloads into one dict."""
    flat: Dict[str, Any] = {}
    for k, v in payload.items():
        if k == "field_data" and isinstance(v, list):
            for f in v:
                if isinstance(f, dict) and f.get("name"):
                    vals = f.get("values") or []
                    flat[str(f["name"]).lower()] = vals[0] if vals else None
        elif isinstance(v, dict):
            flat.update({str(kk).lower(): vv for kk, vv in v.items() if not isinstance(vv, (dict, list))})
        else:
            flat[str(k).lower()] = v
    return flat


def _first(d: Dict[str, Any], *keys: str) -> Optional[str]:
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            return str(v).strip()
    return None


def _money(v: Optional[str]) -> Optional[float]:
    if not v:
        return None
    m = _MONEY.search(v)
    if m:
        return _rules_note(v)["budget_pkr"]
    digits = re.sub(r"[^\d.]", "", v)
    try:
        return float(digits) if digits else None
    except ValueError:
        return None


def ingest_lead(payload: Dict[str, Any], source: str = "website") -> Dict[str, Any]:
    """Create (or update) a lead from any form / ad / portal payload; de-duplicated by phone or e-mail."""
    d = _flatten(payload)
    name = _first(d, "name", "full_name", "fullname", "first_name", "contact_name") or "Unknown"
    if d.get("last_name") and name == _first(d, "first_name"):
        name = f"{name} {d['last_name']}"
    phone = crm_channels.normalise_phone(_first(d, "phone", "phone_number", "mobile", "whatsapp", "contact_number"))
    email = _first(d, "email", "email_address")
    message = _first(d, "message", "comments", "notes", "question", "requirement", "description")
    city_name = _first(d, "city", "location", "area")
    city = next((c for c in core.cities_db if city_name and c.name.lower() == city_name.lower()), None)
    budget = _money(_first(d, "budget", "budget_max", "price", "max_budget"))
    src = (_first(d, "source", "utm_source", "platform") or source).lower()
    prop = _first(d, "property_id", "listing_id")

    existing = next((x for x in core.leads_db if (phone and crm_channels.normalise_phone(x.phone) == phone) or (email and x.email and x.email.lower() == email.lower())), None)
    note = " · ".join(filter(None, [f"[{src}]", message, f"property {prop}" if prop else None]))
    if existing:
        core.crm_log_interaction(entity_type="lead", entity_id=existing.id, summary=f"New enquiry: {note}", channel="web" if src in ("website", "portal") else src,
                                 direction="inbound", agent_id=existing.assigned_agent_id)
        if existing.status in CLOSED_LEAD and existing.status == "lost":
            existing.status = "new"
        existing.updated_at = datetime.now()
        return {"created": False, "lead_id": existing.id, "name": existing.name, "agent_id": existing.assigned_agent_id}
    lead = json.loads(core.crm_add_lead(name=name, email=email, phone=phone, source=src, budget_max=budget,
                                        city_id=city.id if city else None, assigned_agent_id=_pick_agent(city.id if city else None),
                                        notes=note or None,
                                        interest_category=_first(d, "property_type", "category", "interest")))
    return {"created": True, "lead_id": lead["id"], "name": lead["name"], "agent_id": lead.get("assigned_agent_id"), "score": lead.get("score")}


def whatsapp_inbound(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Meta WhatsApp Cloud webhook: each incoming message is logged on its lead (created if new)."""
    handled = 0
    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value", {}) or {}
            names = {c.get("wa_id"): (c.get("profile") or {}).get("name") for c in value.get("contacts", []) or []}
            for m in value.get("messages", []) or []:
                wa = m.get("from")
                text = (m.get("text") or {}).get("body") or (m.get("button") or {}).get("text") or f"[{m.get('type', 'message')}]"
                res = ingest_lead({"name": names.get(wa) or f"WhatsApp {wa}", "phone": wa, "message": text}, source="whatsapp")
                lead = _lead(res["lead_id"])
                if lead and res["created"]:
                    core.crm_log_interaction(entity_type="lead", entity_id=lead.id, summary=text, channel="whatsapp",
                                             direction="inbound", agent_id=lead.assigned_agent_id)
                handled += 1
    return {"handled": handled}
