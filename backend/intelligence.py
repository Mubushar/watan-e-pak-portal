"""Buyer, seller and investor intelligence (framework-free).

Covers three of the roadmap products on one engine:

* **Conversational Homebuying Agent** — parses a natural-language brief, scores
  candidates on GIS/accounting dimensions, finds below-market anomalies (Z-score)
  and pre-computes affordability.
* **Seller Intelligent Pricing & Marketing Agent** — adjusted-comp CMA, a price
  range with confidence, expected days-on-market, net proceeds and a marketing kit.
* **Agentic Investment Screener** — underwriting (after-tax cash flow, DSCR, cap
  rate, IRR), screening into risk-adjusted ranks and portfolio exit alerts.

It reuses ``accounting`` for the mortgage and investment maths, so REST and MCP
report identical numbers.
"""

import math
import re
from typing import Any, Dict, List, Optional

import accounting


BUYER_WEIGHTS: Dict[str, float] = {
    "price_fit": 0.22, "commute": 0.20, "schools": 0.12, "safety": 0.10,
    "amenities": 0.12, "liquidity": 0.08, "condition": 0.08, "size_fit": 0.08,
}
BUDGET_TOLERANCE = 0.08
ANOMALY_Z_THRESHOLD = 1.0
CONTENT_KINDS = ["listing_description", "social_post", "reel_script", "email",
                 "market_report", "video_script"]

_MONEY_SUFFIX = {"k": 1_000, "m": 1_000_000, "lakh": 100_000, "lac": 100_000,
                 "lakhs": 100_000, "crore": 10_000_000, "crores": 10_000_000,
                 "cr": 10_000_000, "million": 1_000_000, "billion": 1_000_000_000}

_CATEGORY_KEYWORDS = {
    "plot": ["plot", "land", "file"], "house": ["house", "home", "villa", "bungalow"],
    "apartment": ["apartment", "flat", "condo", "penthouse"],
    "office": ["office"], "shop": ["shop", "retail", "store"],
    "building": ["building", "tower", "plaza"], "warehouse": ["warehouse", "godown"],
    "floor": ["floor"], "space": ["space"], "shed": ["shed", "factory"],
}
_FEATURE_KEYWORDS = {
    "gated": ["gated", "gated community", "security"], "corner": ["corner"],
    "park_facing": ["park facing", "park-facing", "facing park"], "school": ["school"],
    "mosque": ["mosque", "masjid"], "hospital": ["hospital", "clinic"],
    "market": ["market", "bazaar", "mall", "shopping"], "park": ["park", "garden", "green"],
    "backup_power": ["backup power", "generator", "ups", "solar"],
    "lift": ["lift", "elevator"], "parking": ["parking", "car park", "garage"],
    "basement": ["basement"], "servant_quarter": ["servant quarter", "servant"],
    "corner_plot": ["corner plot"], "new": ["new", "brand new", "under construction"],
}
_CITY_HINTS = ["lahore", "karachi", "islamabad", "rawalpindi", "faisalabad",
               "multan", "peshawar", "quetta", "gujranwala", "hyderabad", "bahawalpur"]


# ============================================================
# Buyer agent
# ============================================================


def _money(token: str) -> Optional[float]:
    token = token.strip().lower().replace(",", "")
    m = re.match(r"^([\d.]+)\s*([a-z]+)?$", token)
    if not m:
        return None
    value = float(m.group(1))
    suffix = m.group(2)
    if suffix:
        for key, mult in _MONEY_SUFFIX.items():
            if suffix.startswith(key):
                return value * mult
        return None
    return value


def parse_requirement(text: str, known_cities: Optional[List[str]] = None) -> Dict[str, Any]:
    """Parse a natural-language buyer brief into a structured requirement."""
    if not text:
        return {"error": "no brief supplied"}
    low = text.lower()
    req: Dict[str, Any] = {"raw": text, "must_have": [], "nice_to_have": []}
    found = 0

    # budget (range or single)
    budget_nums = [_money(t) for t in re.findall(r"([\d.]+\s*(?:k|m|lakh|lac|lakhs|crore|crores|cr|million)?)", low)]
    budget_nums = [b for b in budget_nums if b and b > 1000]
    if budget_nums:
        req["budget_min"] = min(budget_nums)
        req["budget_max"] = max(budget_nums)
        found += 1

    # commute
    mc = re.search(r"(\d+)\s*(?:min|mins|minute|minutes)", low)
    if mc:
        req["max_commute_min"] = int(mc.group(1))
        found += 1
    ct = re.search(r"commute\s*(?:to|into)?\s*([a-z][a-z\s]{2,30})", low)
    if ct:
        req["commute_destination"] = ct.group(1).strip().title()
    elif "city" in low and "commute" in low:
        req["commute_destination"] = "city"

    # bedrooms
    br = re.search(r"(\d+)\s*(?:bed|bedroom|bedrooms|br|bhk)", low)
    if br:
        req["bedrooms"] = int(br.group(1))
        found += 1

    # category / type
    for cat, words in _CATEGORY_KEYWORDS.items():
        if any(w in low for w in words):
            req["category"] = cat
            found += 1
            break
    if "commercial" in low:
        req["use_type"] = "commercial"
    elif "residential" in low:
        req["use_type"] = "residential"

    # city
    cities = known_cities or _CITY_HINTS
    for c in cities:
        if c.lower() in low:
            req["city"] = c
            found += 1
            break

    # family
    fam = re.search(r"family\s*(?:of)?\s*(\d+)", low)
    if fam:
        req["family_size"] = int(fam.group(1))

    # timeline
    tl = re.search(r"(\d+)\s*(?:month|months|year|years)", low)
    if tl and ("within" in low or "timeline" in low or "next" in low):
        value = int(tl.group(1))
        req["timeline_months"] = value * 12 if "year" in tl.group(0) else value

    # features
    for feat, words in _FEATURE_KEYWORDS.items():
        if any(w in low for w in words):
            if ("must" in low and feat in low) or feat in ("gated", "corner"):
                req["must_have"].append(feat)
            else:
                req["nice_to_have"].append(feat)
            found += 1

    req["confidence"] = round(min(0.98, 0.35 + 0.09 * found), 2)
    req["parsed_fields"] = sorted(k for k in req
                                  if k not in ("raw", "must_have", "nice_to_have", "confidence",
                                               "parsed_fields"))
    return req


def _price_fit(price: float, req: Dict[str, Any]) -> float:
    lo, hi = req.get("budget_min"), req.get("budget_max")
    if hi is None:
        return 65.0
    if price <= hi:
        return 100.0
    over = (price - hi) / hi
    return max(0.0, 100.0 - over / BUDGET_TOLERANCE * 140.0)


def _commute_score(req: Dict[str, Any], ctx: Dict[str, Any]) -> float:
    minutes = ctx.get("commute_minutes")
    cap = req.get("max_commute_min")
    if minutes is None:
        return 65.0
    if not cap:
        return max(0.0, 100.0 - minutes * 1.5)
    if minutes <= cap * 0.7:
        return 100.0
    if minutes >= cap * 1.5:
        return 0.0
    return round(max(0.0, 100.0 * (cap * 1.5 - minutes) / (cap * 0.8)), 1)


def score_candidate(req: Dict[str, Any], candidate: Dict[str, Any],
                    ctx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Score one property against a parsed requirement across weighted dimensions."""
    ctx = dict(ctx or {})
    price = float(candidate.get("price") or 0)
    dims: Dict[str, float] = {}
    dims["price_fit"] = round(_price_fit(price, req), 1)
    dims["commute"] = round(_commute_score(req, ctx), 1)
    dims["schools"] = round(float(ctx.get("schools_score", 62)), 1)
    dims["safety"] = round(float(ctx.get("safety_score", 66)), 1)
    dims["amenities"] = round(float(ctx.get("amenities_score", 60)), 1)
    dims["liquidity"] = round(float(ctx.get("liquidity_score", 60)), 1)
    age = float(candidate.get("age_years") or ctx.get("age_years") or 0)
    dims["condition"] = round(float(ctx.get("condition_score", max(40.0, 100.0 - age * 3.0))), 1)
    want_beds = req.get("bedrooms")
    have_beds = candidate.get("bedrooms")
    if want_beds and have_beds:
        dims["size_fit"] = 100.0 if have_beds >= want_beds else max(30.0, 100.0 - (want_beds - have_beds) * 25)
    else:
        dims["size_fit"] = 72.0
    composite = round(sum(dims[k] * w for k, w in BUYER_WEIGHTS.items()), 1)

    reasons: List[str] = []
    if dims["price_fit"] >= 95:
        reasons.append("within budget")
    elif dims["price_fit"] < 60:
        reasons.append("over budget")
    if dims["commute"] >= 80:
        reasons.append("commute within target")
    elif dims["commute"] < 45 and req.get("max_commute_min"):
        reasons.append("commute exceeds target")
    if dims["schools"] >= 75:
        reasons.append("strong school catchment")
    if dims["amenities"] >= 75:
        reasons.append("rich amenities nearby")

    flags: List[str] = []
    if price > (req.get("budget_max") or math.inf):
        flags.append("over_budget")
    if dims["commute"] < 40 and req.get("max_commute_min"):
        flags.append("long_commute")
    if ctx.get("price_vs_area_pct", 0) > 8:
        flags.append("above_area_average")

    return {"candidate_id": candidate.get("id"), "title": candidate.get("title"),
            "price": price, "composite": composite, "dimensions": dims,
            "reasons": reasons, "flags": flags, "band": (
                "excellent" if composite >= 82 else "good" if composite >= 68
                else "fair" if composite >= 52 else "weak")}


def rank_candidates(req: Dict[str, Any], candidates: List[Dict[str, Any]],
                    contexts: Optional[Dict[str, Dict[str, Any]]] = None,
                    limit: int = 10) -> Dict[str, Any]:
    contexts = contexts or {}
    scored = [score_candidate(req, c, contexts.get(str(c.get("id")))) for c in candidates]
    scored.sort(key=lambda r: r["composite"], reverse=True)
    for i, row in enumerate(scored):
        row["rank"] = i + 1
    top = scored[:limit]
    return {"requirement": {k: v for k, v in req.items() if k != "raw"},
            "candidates_considered": len(candidates), "returned": len(top),
            "shortlist": top}


def anomaly_scan(items: List[Dict[str, Any]], price_field: str = "price",
                 area_field: str = "covered_area", group_field: str = "city",
                 threshold: float = ANOMALY_Z_THRESHOLD) -> Dict[str, Any]:
    """Z-score price deviations inside each group; surfaces below-average bargains."""
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for it in items:
        price = it.get(price_field)
        if not price:
            continue
        area = it.get(area_field) or 0
        unit_price = float(price) / float(area) if area else float(price)
        g = str(it.get(group_field) or "all")
        groups.setdefault(g, []).append({"item": it, "unit_price": unit_price})
    results: List[Dict[str, Any]] = []
    for g, rows in groups.items():
        values = [r["unit_price"] for r in rows]
        if len(values) < 2:
            continue
        mean = sum(values) / len(values)
        var = sum((v - mean) ** 2 for v in values) / len(values)
        std = math.sqrt(var) or 1e-9
        for r in rows:
            z = (r["unit_price"] - mean) / std
            deviation_pct = round((r["unit_price"] - mean) / mean * 100, 2) if mean else 0.0
            tag = "underpriced" if z <= -threshold else "overpriced" if z >= threshold else "at_market"
            results.append({
                "id": r["item"].get("id"), "title": r["item"].get("title"),
                "group": g, "price": r["item"].get(price_field),
                "unit_price": round(r["unit_price"], 2), "group_mean": round(mean, 2),
                "z_score": round(z, 2), "deviation_pct": deviation_pct, "tag": tag,
            })
    results.sort(key=lambda r: r["z_score"])
    bargains = [r for r in results if r["tag"] == "underpriced"]
    return {"scanned": len(results), "group_count": len(groups),
            "bargain_count": len(bargains), "threshold": threshold,
            "bargains": bargains[:20], "all": results[:40]}


def affordability(price: float, down_payment_share: float = 0.25,
                  annual_rate: Optional[float] = None, years: Optional[int] = None,
                  monthly_income: Optional[float] = None, property_tax_rate: float = 0.01,
                  holding_monthly: float = 0.0, other_debt_monthly: float = 0.0) -> Dict[str, Any]:
    """Monthly payment, taxes, holding costs and debt-to-income verdict."""
    loan = max(0.0, float(price) * (1 - down_payment_share))
    sched = accounting.mortgage_schedule(loan, annual_rate=annual_rate, years=years)
    if "error" in sched:
        return sched
    payment = sched["payment"]
    tax_monthly = float(price) * property_tax_rate / 12.0
    total_monthly = payment + tax_monthly + holding_monthly
    out = {"price": round(float(price), 2), "down_payment": round(float(price) * down_payment_share, 2),
           "loan_amount": round(loan, 2), "monthly_payment": payment,
           "monthly_property_tax": round(tax_monthly, 2),
           "monthly_holding": round(holding_monthly, 2),
           "total_monthly_outlay": round(total_monthly, 2),
           "total_interest": sched.get("total_interest"),
           "rate": sched.get("annual_rate"), "years": sched.get("years")}
    if monthly_income:
        dti = (total_monthly + other_debt_monthly) / float(monthly_income)
        verdict = ("comfortable" if dti <= 0.30 else "affordable" if dti <= 0.40
                   else "stretched" if dti <= 0.50 else "unaffordable")
        out.update({"monthly_income": monthly_income, "dti": round(dti, 3),
                    "verdict": verdict,
                    "required_income_at_35pct": round(total_monthly / 0.35, 2)})
    return out


# ============================================================
# Seller agent — CMA, proceeds & marketing
# ============================================================

CMA_ADJUSTMENTS: Dict[str, float] = {
    "area_per_sqft": 0.0,   # filled at runtime from subject unit price
    "age_per_year": -0.005, "condition_per_point": 0.04, "location_per_point": 0.05,
}


def adjust_comps(subject: Dict[str, Any], comps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Adjust comparable sales toward the subject (area, age, condition, location)."""
    s_area = float(subject.get("covered_area") or subject.get("plot_area") or 0) or 1.0
    s_unit = float(subject.get("price") or 0) / s_area if subject.get("price") else 0.0
    if not s_unit:
        prices = [c.get("price") for c in comps if c.get("price")]
        s_unit = (sum(prices) / len(prices) / s_area) if prices else 10000.0
    adjusted: List[Dict[str, Any]] = []
    for c in comps:
        c_area = float(c.get("covered_area") or c.get("plot_area") or s_area) or s_area
        c_unit = float(c.get("price") or 0) / c_area if c.get("price") else s_unit
        factor = 1.0
        factor += (s_area - c_area) / max(s_area, c_area) * 0.30
        age_delta = float(subject.get("age_years") or 0) - float(c.get("age_years") or 0)
        factor += age_delta * CMA_ADJUSTMENTS["age_per_year"]
        cond_delta = float(subject.get("condition_score") or 3) - float(c.get("condition_score") or 3)
        factor += cond_delta * CMA_ADJUSTMENTS["condition_per_point"]
        loc_delta = float(subject.get("location_score") or 3) - float(c.get("location_score") or 3)
        factor += loc_delta * CMA_ADJUSTMENTS["location_per_point"]
        adj_unit = c_unit * factor
        adjusted.append({"comp_id": c.get("id"), "title": c.get("title"),
                         "raw_price": c.get("price"), "area": c_area,
                         "raw_unit_price": round(c_unit, 2), "adjust_factor": round(factor, 3),
                         "adjusted_unit_price": round(adj_unit, 2),
                         "adjusted_price": round(adj_unit * s_area, 2)})
    return adjusted


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * pct
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    if lo == hi:
        return s[int(k)]
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def pricing_cma(subject: Dict[str, Any], comps: List[Dict[str, Any]],
                market: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Comparative market analysis: adjusted comps → price range, confidence, DOM."""
    market = dict(market or {})
    area = float(subject.get("covered_area") or subject.get("plot_area") or 0)
    if not comps:
        return {"error": "no comparable sales supplied"}
    adjusted = adjust_comps(subject, comps)
    units = [a["adjusted_unit_price"] for a in adjusted]
    low_unit = _percentile(units, 0.25)
    mid_unit = _percentile(units, 0.50)
    high_unit = _percentile(units, 0.75)
    spread = (high_unit - low_unit) / mid_unit if mid_unit else 1.0
    confidence = round(max(0.35, min(0.95, 0.9 - spread * 0.6 + min(0.15, len(comps) * 0.02))), 2)
    # never over-confident on a thin comp set
    confidence = round(min(confidence, 0.45 + min(len(comps), 6) * 0.08), 2)
    area = area or float(subject.get("area") or 1)
    price_range = {"low": round(low_unit * area), "target": round(mid_unit * area),
                   "high": round(high_unit * area)}
    list_price = round(price_range["target"] * (1.0 + float(market.get("aspiration") or 0.0)))
    dom_base = float(market.get("average_dom") or 45)
    over = (list_price - price_range["target"]) / price_range["target"] if price_range["target"] else 0
    expected_dom = round(dom_base * (1 + max(0.0, over) * 4 - min(0.2, (over < 0) * 0.2)), 0)
    strategy = ("price at target for a fast, confident sale" if confidence >= 0.75
                else "price slightly below target to anchor competing offers")
    return {"subject": {"title": subject.get("title"), "area": area},
            "comp_count": len(comps), "adjusted_comps": adjusted,
            "price_range": price_range, "recommended_list_price": list_price,
            "confidence": confidence, "expected_days_on_market": expected_dom,
            "price_per_sqft": {"low": round(low_unit, 2), "target": round(mid_unit, 2),
                               "high": round(high_unit, 2)},
            "pricing_strategy": strategy,
            "rationale": [
                f"{len(comps)} comparable sales adjusted to the subject",
                f"dispersion {round(spread * 100)}% between the 25th and 75th percentile",
                f"confidence {'high' if confidence >= 0.75 else 'moderate' if confidence >= 0.55 else 'low'}",
            ]}


def net_proceeds(price: float, commission_rate: float = 0.02, other_cost_rate: float = 0.01,
                 mortgage_payoff: float = 0.0, cost_basis: Optional[float] = None,
                 capital_gains_rate: Optional[float] = None) -> Dict[str, Any]:
    """Seller's net cash after commission, costs, payoff and capital-gains estimate."""
    commission = float(price) * commission_rate
    other = float(price) * other_cost_rate
    gross_after_costs = float(price) - commission - other
    gain = None
    tax = 0.0
    if cost_basis is not None:
        gain = float(price) - float(cost_basis) - commission - other
        tax = max(0.0, gain) * (capital_gains_rate or 0.0)
    net = gross_after_costs - float(mortgage_payoff) - tax
    return {"price": round(float(price), 2), "commission": round(commission, 2),
            "other_costs": round(other, 2), "mortgage_payoff": round(float(mortgage_payoff), 2),
            "capital_gains_tax": round(tax, 2), "estimated_gain": round(gain, 2) if gain is not None else None,
            "net_proceeds": round(net, 2),
            "net_proceeds_pct": round(net / float(price) * 100, 2) if price else 0.0}


def generate_listing_assets(listing: Dict[str, Any], lang: str = "en",
                            tone: str = "professional") -> Dict[str, Any]:
    """Deterministic marketing kit: description, posts, email, video script, staging."""
    title = listing.get("title") or "Property"
    city = listing.get("city") or ""
    scheme = listing.get("scheme") or ""
    price = float(listing.get("price") or 0)
    area = listing.get("covered_area") or listing.get("plot_area")
    beds = listing.get("bedrooms")
    features = listing.get("features") or []
    location = ", ".join(x for x in (scheme, city) if x)
    price_txt = f"PKR {price:,.0f}" if price else "price on request"
    bed_txt = f"{beds}-bedroom " if beds else ""
    area_txt = f"{float(area):,.0f} sqft " if area else ""

    headline = f"{bed_txt}{title} in {location} — {price_txt}".strip()
    description = (
        f"{headline}.\n\nThis {area_txt}property in {location} offers a compelling blend of "
        f"location, value and lifestyle. {'Built with ' + ', '.join(features[:4]) + '. ' if features else ''}"
        f"Priced at {price_txt}, it suits owner-occupiers and investors alike. "
        f"Book a viewing to see the full potential."
    )
    bullets = [
        f"{area_txt.strip() or 'Well-proportioned'} layout",
        f"Prime {location or 'city'} location",
        f"Priced at {price_txt}",
    ] + [f.title() for f in features[:5]]

    tone_line = {"professional": "A refined choice for discerning buyers.",
                 "luxury": "An exceptional residence for the most discerning buyer.",
                 "urgent": "Priced to sell — enquire today.",
                 "family": "A warm family home in a settled neighbourhood."}[tone]
    posts = {
        "facebook": f"🏡 {headline}\n\n{description[:280]}...\n\n{bullets[0]} · {bullets[1]}\n#realestate #{city or 'Pakistan'}",
        "instagram": f"✨ Just listed in {location or city}\n{headline}\n\n{bullets[0]}\n#property #homes {('#' + city.replace(' ', '')) if city else ''}",
        "linkedin": f"New listing — {headline}. {tone_line} Ideal for investors seeking {city or 'a prime'} exposure. Details on request.",
        "whatsapp": f"Hi! New listing: {headline}. {area_txt}Interested? I can arrange a viewing this week.",
    }
    email_subject = f"Just listed: {bed_txt}{title} in {location}"
    email_body = f"Hello,\n\n{description}\n\nHighlights:\n- " + "\n- ".join(bullets) + \
                 "\n\nReply to arrange a viewing.\n"
    video_script = (
        f"[0:00] Aerial drone shot over {location}.\n"
        f"[0:05] Title card: {headline}.\n"
        f"[0:10] Walk-through of the {area_txt}interior; highlight {bullets[0].lower()}.\n"
        f"[0:25] Neighbourhood B-roll — schools, parks, access roads.\n"
        f"[0:40] Closing card: {price_txt} · book your viewing."
    )
    staging = [
        "Declutter and depersonalise every room",
        "Neutral, warm lighting for photos and viewings",
        "Add greenery at the entrance and terrace",
        "Virtual staging for any empty rooms in the listing photos",
        f"Lead with: {bullets[0]}",
    ]
    keywords = [w for w in [title, city, scheme, listing.get("category"), "for sale", "property"]
                if w]
    hashtags = ["#" + str(k).replace(" ", "") for k in keywords if k][:8]
    return {"headline": headline, "description": description, "bullets": bullets,
            "tone": tone, "social_posts": posts, "email": {"subject": email_subject, "body": email_body},
            "video_script": video_script, "staging_suggestions": staging,
            "keywords": keywords, "hashtags": hashtags, "lang": lang}


# ============================================================
# Investment screener
# ============================================================


def underwrite(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Underwrite a deal: NOI, debt service, cash flow, DSCR, cap rate, IRR (after tax)."""
    price = float(inputs.get("purchase_price") or 0)
    if price <= 0:
        return {"error": "purchase_price is required"}
    rent = float(inputs.get("annual_rent") or 0)
    if not rent and inputs.get("monthly_rent"):
        rent = float(inputs["monthly_rent"]) * 12
    vacancy = float(inputs.get("vacancy_rate") or 0.05)
    opex_rate = float(inputs.get("operating_expense_rate") or 0.30)
    down = float(inputs.get("down_payment_share") or 0.25)
    loan = price * (1 - down)
    hold = int(inputs.get("hold_years") or 10)
    appreciation = float(inputs.get("appreciation_rate") or 0.06)
    exit_cap = float(inputs.get("exit_cap_rate") or 0.07)
    tax_rate = float(inputs.get("tax_rate") or 0.0)

    effective_income = rent * (1 - vacancy)
    opex = effective_income * opex_rate
    noi = effective_income - opex
    sched = accounting.mortgage_schedule(loan, annual_rate=inputs.get("loan_rate"),
                                         years=int(inputs.get("loan_years") or 20)) if loan else {"payment": 0.0}
    annual_debt = float(sched.get("payment") or 0.0) * 12
    pre_tax_cf = noi - annual_debt
    dscr = round(noi / annual_debt, 2) if annual_debt else None
    cap = round(noi / price, 4)
    coc = round(pre_tax_cf / (price * down), 4) if down else None
    taxable = noi - (loan * float(inputs.get("interest_deduct_rate") or 0.0))
    after_tax_cf = pre_tax_cf - max(0.0, taxable) * tax_rate
    exit_value = price * (1 + appreciation) ** hold if not exit_cap else noi / exit_cap * (1 + appreciation) ** (hold - 1)
    equity_at_exit = exit_value - loan
    cashflows = [-(price * down)] + [after_tax_cf] * hold
    cashflows[-1] += equity_at_exit
    metrics = accounting.investment_metrics(cashflows, inputs.get("discount_rate"))
    score, grade, drivers = _risk_adjusted(cap, dscr, coc, metrics.get("irr"), appreciation)
    return {"inputs": {"price": price, "loan": round(loan, 2), "down_payment": round(price * down, 2)},
            "income": {"gross_rent": round(rent, 2), "effective_income": round(effective_income, 2),
                       "operating_expenses": round(opex, 2), "noi": round(noi, 2)},
            "debt": {"annual_debt_service": round(annual_debt, 2), "dscr": dscr},
            "returns": {"cap_rate": cap, "cash_on_cash": coc, "pre_tax_cash_flow": round(pre_tax_cf, 2),
                        "after_tax_cash_flow": round(after_tax_cf, 2), "irr": metrics.get("irr"),
                        "npv": metrics.get("npv"), "equity_multiple": metrics.get("equity_multiple"),
                        "exit_value": round(exit_value, 2), "equity_at_exit": round(equity_at_exit, 2)},
            "risk_adjusted_score": score, "grade": grade, "drivers": drivers,
            "flags": [f for f in [
                "negative cash flow" if pre_tax_cf < 0 else None,
                "DSCR below 1.2" if (dscr is not None and dscr < 1.2) else None,
                "thin cap rate" if cap < 0.05 else None] if f]}


def _risk_adjusted(cap: float, dscr: Optional[float], coc: Optional[float],
                   irr: Optional[float], appreciation: float) -> tuple:
    cap_pts = min(40.0, cap * 100 * 5)
    dscr_pts = max(0.0, min(25.0, ((dscr or 0) - 0.8) / 0.8 * 25)) if dscr else 10.0
    coc_pts = min(20.0, max(-5.0, (coc or 0) * 100 * 1.2))
    irr_pts = min(15.0, (irr or 0) * 100 * 0.6)
    score = round(max(0.0, min(100.0, cap_pts + dscr_pts + coc_pts + irr_pts)), 1)
    grade = "A" if score >= 75 else "B" if score >= 60 else "C" if score >= 45 else "D"
    drivers = [f"cap {round(cap * 100, 2)}%", f"DSCR {dscr}", f"CoC {round((coc or 0) * 100, 1)}%",
               f"IRR {round((irr or 0) * 100, 1)}%"]
    return score, grade, drivers


def screen_investments(candidates: List[Dict[str, Any]],
                       criteria: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Filter a candidate pool to the top risk-adjusted opportunities."""
    criteria = dict(criteria or {})
    max_price = criteria.get("max_price")
    min_cap = criteria.get("min_cap_rate")
    min_dscr = criteria.get("min_dscr")
    cities = [c.lower() for c in criteria.get("cities", [])] if criteria.get("cities") else None
    kinds = [k.lower() for k in criteria.get("property_types", [])] if criteria.get("property_types") else None

    passed: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    for c in candidates:
        uw = underwrite(c)
        if "error" in uw:
            continue
        reasons = []
        if max_price and uw["inputs"]["price"] > max_price:
            reasons.append("over max price")
        if cities and str(c.get("city") or "").lower() not in cities:
            reasons.append("city out of scope")
        if kinds and str(c.get("category") or "").lower() not in kinds:
            reasons.append("type out of scope")
        if min_cap and uw["returns"]["cap_rate"] < min_cap:
            reasons.append("cap rate below floor")
        if min_dscr and uw["debt"]["dscr"] is not None and uw["debt"]["dscr"] < min_dscr:
            reasons.append("DSCR below floor")
        row = {"id": c.get("id"), "title": c.get("title"), "city": c.get("city"),
               "cap_rate": uw["returns"]["cap_rate"], "dscr": uw["debt"]["dscr"],
               "irr": uw["returns"]["irr"], "cash_flow": uw["returns"]["after_tax_cash_flow"],
               "score": uw["risk_adjusted_score"], "grade": uw["grade"]}
        if reasons:
            row["reasons"] = reasons
            rejected.append(row)
        else:
            passed.append(row)
    passed.sort(key=lambda r: r["score"], reverse=True)
    for i, row in enumerate(passed):
        row["rank"] = i + 1
    top_pct = round(100.0 * len(passed) / len(candidates), 1) if candidates else 0.0
    return {"criteria": criteria, "considered": len(candidates), "passed": len(passed),
            "rejected": len(rejected), "pass_rate_pct": top_pct,
            "top_picks": passed[:10], "rejected_sample": rejected[:10]}


def portfolio_alerts(holdings: List[Dict[str, Any]],
                     signals: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Proactive investor alerts: exit windows, refinance and rent-index signals."""
    signals = dict(signals or {})
    rate = float(signals.get("interest_rate") or 0.18)
    rent_index_change = float(signals.get("rent_index_change") or 0.0)
    supply_change = float(signals.get("supply_change") or 0.0)
    market_heat = float(signals.get("market_heat") or 0.5)
    alerts: List[Dict[str, Any]] = []
    for h in holdings:
        held = float(h.get("hold_years") or 0)
        target = float(h.get("target_hold_years") or 7)
        value = float(h.get("current_value") or 0)
        purchase = float(h.get("purchase_value") or 0)
        gain = (value - purchase) / purchase if purchase else 0.0
        if held >= target or (market_heat >= 0.75 and gain > 0.35):
            alerts.append({"id": h.get("id"), "title": h.get("title"),
                           "type": "exit_window", "severity": "high",
                           "message": f"Exit window closing — held {held:.0f}y of {target:.0f}y target, "
                                      f"paper gain {round(gain * 100)}%."})
        if rate <= 0.145 and h.get("loan_balance"):
            alerts.append({"id": h.get("id"), "title": h.get("title"),
                           "type": "refinance", "severity": "medium",
                           "message": f"Rates at {round(rate * 100, 1)}% — refinance the "
                                      f"{float(h.get('loan_balance')):,.0f} balance to cut debt service."})
        if rent_index_change <= -0.03 or supply_change >= 0.08:
            alerts.append({"id": h.get("id"), "title": h.get("title"),
                           "type": "market_risk", "severity": "medium",
                           "message": "Softening rents / rising supply — consider a rent review or "
                                      "repositioning."})
    return {"holdings": len(holdings), "alerts": alerts, "count": len(alerts),
            "by_type": {t: sum(1 for a in alerts if a["type"] == t)
                        for t in ("exit_window", "refinance", "market_risk")},
            "signals": signals}
