"""
Portal content & advertising engine for the Real Estate Portal
==============================================================

Everything the *public-facing* portal needs beyond the catalogue itself:

* **Content pages** — about, mission, services, team, FAQ, policies, careers …
  prose pages with highlights, bullets and FAQ blocks (a tiny CMS).
* **Company history** — a dated timeline of milestones, expansions, awards,
  technology adoptions and partnerships.
* **Contact directory** — phone / e-mail / WhatsApp / office / hours / social
  channels, optionally scoped to a city or scheme.
* **Success stories** — case studies, client testimonials and delivery
  milestones with metrics, quotes and references to real portal entities.
* **Advertising** — creatives placed in named *slots* (hero, banner, sidebar,
  in-feed, footer, newsletter), tagged by category (smart technology,
  construction techniques, building materials, tools, finance, solar, security …),
  with targeting (city / scheme / language), scheduling windows, weighted
  rotation and impression / click / CTR performance tracking.

No MCP or FastAPI code lives here: ``server.py`` exposes these functions over MCP
and ``api.py`` reuses the very same functions over REST. ``gis.py`` renders the
plain dicts this module returns into the themed, bilingual portal HTML.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# ============================================================
# CONFIGURATION
# ============================================================

CONTENT_CONFIG: Dict[str, Any] = {
    "site_name": "Arz-e-Pak Real Estate Portal",
    "tagline": "Pakistan's smart, data-driven property marketplace",
    "default_language": "en",
    "supported_languages": ["en", "ur"],
}

ADS_CONFIG: Dict[str, Any] = {
    "currency": "PKR",
    "currency_symbol": "Rs",
    "sponsored_label": "Sponsored",
    "house_ad_title": "Advertise here",
    "house_ad_body": "Reach thousands of buyers, investors and developers across Pakistan.",
    "max_per_slot": 6,
    "default_slot": "infeed",
    "impression_weight_floor": 1.0,
}

# name -> human label, in a sensible display order
AD_CATEGORIES: Dict[str, str] = {
    "smart_technology": "Smart home & building technology",
    "construction_technique": "Modern construction techniques",
    "materials": "Building materials & availability",
    "tools_equipment": "Tools, machinery & equipment",
    "solar_energy": "Solar & renewable energy",
    "water": "Water supply, filtration & plumbing",
    "security": "Security & access control",
    "elevators": "Elevators, lifts & parking",
    "interiors": "Interiors, finishes & furnishing",
    "landscaping": "Landscaping & outdoor",
    "finance": "Home finance & mortgages",
    "insurance": "Property & title insurance",
    "legal": "Legal, titling & documentation",
    "services": "Moving, maintenance & other services",
}

# name -> human label
AD_SLOTS: Dict[str, str] = {
    "hero": "Homepage hero banner",
    "banner": "Full-width banner",
    "sidebar": "Sidebar tile",
    "infeed": "In-feed native ad",
    "footer": "Footer strip",
    "newsletter": "Newsletter block",
}

AD_STATUSES = ["active", "paused", "draft", "expired"]

CONTENT_CATEGORIES = [
    "about", "mission", "services", "why-us", "team", "faq", "careers",
    "policy", "legal", "help", "news",
]

HISTORY_KINDS = [
    "founding", "milestone", "expansion", "technology", "award",
    "partnership", "financial", "recognition",
]

CONTACT_TYPES = [
    "phone", "email", "whatsapp", "address", "office", "hours",
    "social", "website", "chat", "helpline",
]

STORY_TYPES = ["case_study", "testimonial", "project", "investment", "milestone"]

# The canonical portal front-page layout. ``server.py`` fills each block from
# the stores; ``gis.build_portal_html`` renders the blocks in this order, so the
# advertisement sections are *decorated into* the editorial flow.
PORTAL_LAYOUT: List[Dict[str, Any]] = [
    {"kind": "hero", "ad_slot": "hero"},
    {"kind": "ads", "slot": "banner", "category": "smart_technology",
     "heading": "Smart technology for modern living"},
    {"kind": "page", "page": "about"},
    {"kind": "stats", "heading": "Portal at a glance"},
    {"kind": "ads", "slot": "infeed", "category": "construction_technique",
     "heading": "Build smarter — modern construction techniques"},
    {"kind": "page", "page": "services"},
    {"kind": "ads", "slot": "sidebar", "category": "materials",
     "heading": "Building materials — availability & rates"},
    {"kind": "stories", "heading": "Success stories"},
    {"kind": "timeline", "heading": "Our journey"},
    {"kind": "ads", "slot": "infeed", "category": "solar_energy",
     "heading": "Solar & renewable energy"},
    {"kind": "page", "page": "why-us"},
    {"kind": "contact", "heading": "Contact us"},
    {"kind": "ads", "slot": "footer", "heading": "Featured partners"},
]


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _today() -> str:
    return datetime.now().date().isoformat()


def _new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


def _m(model: BaseModel) -> Dict[str, Any]:
    return model.model_dump(mode="json")


# ============================================================
# MODELS
# ============================================================


class PortalPage(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("pg_"))
    key: str                                   # slug / primary key, e.g. "about"
    title: str
    category: str = "about"
    subtitle: Optional[str] = None
    summary: Optional[str] = None
    body: List[str] = Field(default_factory=list)          # paragraphs
    highlights: List[Dict[str, str]] = Field(default_factory=list)  # {label, value, sub}
    bullets: List[str] = Field(default_factory=list)
    faqs: List[Dict[str, str]] = Field(default_factory=list)        # {question, answer}
    tags: List[str] = Field(default_factory=list)
    nav_label: Optional[str] = None
    show_in_nav: bool = True
    order: int = 100
    status: str = "published"                  # published | draft | archived
    updated_at: str = Field(default_factory=_now)


class HistoryEntry(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("hs_"))
    year: int
    month: Optional[int] = None
    title: str
    description: str
    kind: str = "milestone"
    tags: List[str] = Field(default_factory=list)
    featured: bool = False


class ContactChannel(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("ct_"))
    channel_type: str                          # phone | email | whatsapp | office | hours | …
    label: str
    value: str
    url: Optional[str] = None
    hours: Optional[str] = None
    city_id: Optional[str] = None
    scheme_id: Optional[str] = None
    region: Optional[str] = None
    priority: int = 100
    is_primary: bool = False
    notes: Optional[str] = None


class SuccessStory(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("ss_"))
    title: str
    story_type: str = "case_study"
    client_name: Optional[str] = None
    client_role: Optional[str] = None
    quote: Optional[str] = None
    rating: Optional[float] = None
    location: Optional[str] = None
    city_id: Optional[str] = None
    scheme_id: Optional[str] = None
    property_id: Optional[str] = None
    project_id: Optional[str] = None
    narrative: List[str] = Field(default_factory=list)
    metrics: List[Dict[str, str]] = Field(default_factory=list)     # {label, value}
    highlights: List[str] = Field(default_factory=list)
    image_url: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    featured: bool = False
    date: Optional[str] = None


class Advertisement(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("ad_"))
    title: str
    headline: str
    body: Optional[str] = None
    advertiser: str = ""
    category: str = "services"
    slot: str = "infeed"
    keywords: List[str] = Field(default_factory=list)
    cta_label: Optional[str] = None
    cta_url: Optional[str] = None
    media_url: Optional[str] = None
    image_url: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    contact: Optional[str] = None
    phone: Optional[str] = None
    price_text: Optional[str] = None            # e.g. "From Rs 2,450 / bag"
    offer: Optional[str] = None
    city_id: Optional[str] = None
    scheme_id: Optional[str] = None
    lang: Optional[str] = None                  # None = all languages
    priority: int = 100
    weight: float = 1.0
    status: str = "active"
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    budget: float = 0.0
    spend: float = 0.0
    impressions: int = 0
    clicks: int = 0
    created_at: str = Field(default_factory=_now)


# ============================================================
# STORES
# ============================================================

pages_db: List[PortalPage] = []
history_db: List[HistoryEntry] = []
contacts_db: List[ContactChannel] = []
stories_db: List[SuccessStory] = []
ads_db: List[Advertisement] = []


# ============================================================
# LOOKUPS
# ============================================================


def find_page(key_or_id: Optional[str]) -> Optional[PortalPage]:
    if not key_or_id:
        return None
    k = str(key_or_id).strip().lower()
    return next((p for p in pages_db if p.key.lower() == k or p.id == key_or_id), None)


def list_pages(category: Optional[str] = None, status: str = "published",
               tag: Optional[str] = None, nav_only: bool = False) -> List[PortalPage]:
    rows = list(pages_db)
    if status and status != "all":
        rows = [p for p in rows if p.status == status]
    if category:
        rows = [p for p in rows if p.category == category]
    if tag:
        rows = [p for p in rows if tag in p.tags]
    if nav_only:
        rows = [p for p in rows if p.show_in_nav]
    return sorted(rows, key=lambda p: (p.order, p.title))


def list_history(kind: Optional[str] = None, since: Optional[int] = None,
                 until: Optional[int] = None, featured: Optional[bool] = None) -> List[HistoryEntry]:
    rows = list(history_db)
    if kind:
        rows = [h for h in rows if h.kind == kind]
    if since is not None:
        rows = [h for h in rows if h.year >= since]
    if until is not None:
        rows = [h for h in rows if h.year <= until]
    if featured is not None:
        rows = [h for h in rows if h.featured == featured]
    return sorted(rows, key=lambda h: (h.year, h.month or 0, h.title))


def list_contacts(channel_type: Optional[str] = None, city_id: Optional[str] = None,
                  scheme_id: Optional[str] = None, primary_only: bool = False) -> List[ContactChannel]:
    rows = list(contacts_db)
    if channel_type:
        rows = [c for c in rows if c.channel_type == channel_type]
    if city_id:
        rows = [c for c in rows if c.city_id in (None, city_id)]
    if scheme_id:
        rows = [c for c in rows if c.scheme_id in (None, scheme_id)]
    if primary_only:
        rows = [c for c in rows if c.is_primary]
    return sorted(rows, key=lambda c: (c.priority, c.label))


def list_stories(story_type: Optional[str] = None, city_id: Optional[str] = None,
                 scheme_id: Optional[str] = None, featured: Optional[bool] = None,
                 tag: Optional[str] = None) -> List[SuccessStory]:
    rows = list(stories_db)
    if story_type:
        rows = [s for s in rows if s.story_type == story_type]
    if city_id:
        rows = [s for s in rows if s.city_id == city_id]
    if scheme_id:
        rows = [s for s in rows if s.scheme_id == scheme_id]
    if featured is not None:
        rows = [s for s in rows if s.featured == featured]
    if tag:
        rows = [s for s in rows if tag in s.tags]
    return sorted(rows, key=lambda s: (not s.featured, s.title))


def find_ad(ad_id: Optional[str]) -> Optional[Advertisement]:
    return next((a for a in ads_db if a.id == ad_id), None)


def list_ads(category: Optional[str] = None, slot: Optional[str] = None,
             status: Optional[str] = None, advertiser: Optional[str] = None,
             tag: Optional[str] = None) -> List[Advertisement]:
    rows = list(ads_db)
    if category:
        rows = [a for a in rows if a.category == category]
    if slot:
        rows = [a for a in rows if a.slot == slot]
    if status:
        rows = [a for a in rows if a.status == status]
    if advertiser:
        rows = [a for a in rows if advertiser.lower() in a.advertiser.lower()]
    if tag:
        rows = [a for a in rows if tag in a.tags]
    return sorted(rows, key=lambda a: (-a.priority, a.title))


# ============================================================
# SCHEDULING & ROTATION
# ============================================================


def _within_window(ad: Advertisement, as_of: Optional[str] = None) -> bool:
    day = as_of or _today()
    if ad.valid_from and day < str(ad.valid_from)[:10]:
        return False
    if ad.valid_until and day > str(ad.valid_until)[:10]:
        return False
    return True


def is_live(ad: Advertisement, as_of: Optional[str] = None) -> bool:
    return ad.status == "active" and _within_window(ad, as_of)


def _targets(ad: Advertisement, city_id: Optional[str], scheme_id: Optional[str],
             lang: Optional[str]) -> bool:
    if ad.city_id and city_id and ad.city_id != city_id:
        return False
    if ad.scheme_id and scheme_id and ad.scheme_id != scheme_id:
        return False
    if ad.lang and lang and ad.lang != lang:
        return False
    return True


def active_ads(slot: Optional[str] = None, category: Optional[str] = None,
               city_id: Optional[str] = None, scheme_id: Optional[str] = None,
               lang: Optional[str] = None, limit: Optional[int] = None,
               as_of: Optional[str] = None) -> List[Advertisement]:
    """Live, in-window, on-target creatives, ranked by priority then by a
    deliverable-weighted rotation (least-shown first) so exposure is shared."""
    rows = [a for a in list_ads(slot=slot, category=category) if is_live(a, as_of)]
    rows = [a for a in rows if _targets(a, city_id, scheme_id, lang)]
    rows.sort(key=lambda a: (-a.priority, a.impressions / max(a.weight, ADS_CONFIG["impression_weight_floor"]), a.id))
    cap = limit if limit is not None else ADS_CONFIG["max_per_slot"]
    return rows[:cap]


# ============================================================
# PERFORMANCE TRACKING
# ============================================================


def record_ad_event(ad_id: str, event: str = "impression", count: int = 1) -> Dict[str, Any]:
    """Record ``impression`` or ``click`` events (and derive spend on impressions)."""
    ad = find_ad(ad_id)
    if not ad:
        return {"error": f"Unknown advertisement: {ad_id}"}
    event = (event or "impression").strip().lower()
    count = max(1, int(count))
    if event in ("impression", "view", "views"):
        ad.impressions += count
        if ad.budget > 0 and ad.spend >= ad.budget:
            ad.status = "paused"
    elif event in ("click", "clicks"):
        ad.clicks += count
    elif event in ("spend", "charge"):
        ad.spend = round(ad.spend + count, 2)
    else:
        return {"error": "event must be one of: impression, click, spend"}
    return {"id": ad.id, "event": event, "count": count,
            "impressions": ad.impressions, "clicks": ad.clicks,
            "ctr": _ctr(ad), "status": ad.status}


def _ctr(ad: Advertisement) -> float:
    return round(ad.clicks / ad.impressions, 4) if ad.impressions else 0.0


def ad_view(ad: Advertisement) -> Dict[str, Any]:
    view = _m(ad)
    view["category_label"] = AD_CATEGORIES.get(ad.category, ad.category)
    view["slot_label"] = AD_SLOTS.get(ad.slot, ad.slot)
    view["ctr"] = _ctr(ad)
    view["remaining_budget"] = round(max(0.0, ad.budget - ad.spend), 2)
    view["live"] = is_live(ad)
    return view


def ad_performance(ad_id: Optional[str] = None) -> Dict[str, Any]:
    """Impression / click / CTR performance for one ad or the whole book."""
    if ad_id:
        ad = find_ad(ad_id)
        if not ad:
            return {"error": f"Unknown advertisement: {ad_id}"}
        return {"ad": ad_view(ad)}
    by_slot: Dict[str, Dict[str, Any]] = {}
    by_category: Dict[str, Dict[str, Any]] = {}
    impressions = clicks = spend = budget = 0
    for ad in ads_db:
        impressions += ad.impressions
        clicks += ad.clicks
        spend += ad.spend
        budget += ad.budget
        for bucket, key in ((by_slot, ad.slot), (by_category, ad.category)):
            row = bucket.setdefault(key, {"impressions": 0, "clicks": 0, "spend": 0.0, "ads": 0})
            row["impressions"] += ad.impressions
            row["clicks"] += ad.clicks
            row["spend"] = round(row["spend"] + ad.spend, 2)
            row["ads"] += 1
    for bucket in (by_slot, by_category):
        for row in bucket.values():
            row["ctr"] = round(row["clicks"] / row["impressions"], 4) if row["impressions"] else 0.0
    top = sorted(ads_db, key=lambda a: (-_ctr(a), -a.clicks))
    return {
        "totals": {
            "ads": len(ads_db), "live": sum(1 for a in ads_db if is_live(a)),
            "impressions": impressions, "clicks": clicks,
            "ctr": round(clicks / impressions, 4) if impressions else 0.0,
            "spend": round(spend, 2), "budget": round(budget, 2),
            "remaining_budget": round(max(0.0, budget - spend), 2),
        },
        "by_slot": by_slot,
        "by_category": by_category,
        "top_performers": [
            {"id": a.id, "title": a.title, "category": a.category, "slot": a.slot,
             "impressions": a.impressions, "clicks": a.clicks, "ctr": _ctr(a)}
            for a in top[:5] if a.impressions or a.clicks
        ],
    }


# ============================================================
# SITE ASSEMBLY  (feeds the HTML renderer in gis.py)
# ============================================================


def navigation() -> List[Dict[str, Any]]:
    """Nav menu derived from published, nav-visible pages."""
    return [
        {"key": p.key, "label": p.nav_label or p.title, "category": p.category}
        for p in list_pages(nav_only=True)
    ]


def content_overview() -> Dict[str, Any]:
    """Counts and breakdowns for the whole content + advertising book."""
    cats: Dict[str, int] = {}
    for ad in ads_db:
        cats[ad.category] = cats.get(ad.category, 0) + 1
    slots: Dict[str, int] = {}
    for ad in ads_db:
        slots[ad.slot] = slots.get(ad.slot, 0) + 1
    return {
        "site": CONTENT_CONFIG,
        "counts": {
            "pages": len(pages_db), "history": len(history_db), "contacts": len(contacts_db),
            "success_stories": len(stories_db), "advertisements": len(ads_db),
            "live_ads": sum(1 for a in ads_db if is_live(a)),
        },
        "pages_by_category": _tally(p.category for p in pages_db),
        "history_by_kind": _tally(h.kind for h in history_db),
        "contacts_by_type": _tally(c.channel_type for c in contacts_db),
        "stories_by_type": _tally(s.story_type for s in stories_db),
        "ads_by_category": cats,
        "ads_by_slot": slots,
        "ad_categories": AD_CATEGORIES,
        "ad_slots": AD_SLOTS,
    }


def _tally(values: Any) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return out


def ad_section(slot: str, category: Optional[str] = None, city_id: Optional[str] = None,
               scheme_id: Optional[str] = None, lang: Optional[str] = None,
               limit: Optional[int] = None, heading: Optional[str] = None) -> Dict[str, Any]:
    """A ready-to-render advertisement section (used by the portal page + REST)."""
    ads = active_ads(slot=slot, category=category, city_id=city_id, scheme_id=scheme_id,
                     lang=lang, limit=limit)
    return {
        "kind": "ads",
        "slot": slot,
        "slot_label": AD_SLOTS.get(slot, slot),
        "category": category,
        "category_label": AD_CATEGORIES.get(category) if category else None,
        "heading": heading or (AD_CATEGORIES.get(category) if category else AD_SLOTS.get(slot, slot)),
        "count": len(ads),
        "ads": [ad_view(a) for a in ads],
    }


def build_site(lang: Optional[str] = None, city_id: Optional[str] = None,
               scheme_id: Optional[str] = None) -> Dict[str, Any]:
    """Assemble the full portal site content: nav, layout blocks, content and ads.

    This is the single structure ``gis.build_portal_html`` renders, and the same
    data the REST/MCP layers return, so the portal page and the APIs never drift.
    """
    pages = {p.key: _m(p) for p in list_pages()}
    site = {
        "config": CONTENT_CONFIG,
        "navigation": navigation(),
        "pages": pages,
        "history": [_m(h) for h in list_history()],
        "contacts": [_m(c) for c in list_contacts(city_id=city_id, scheme_id=scheme_id)],
        "stories": [_m(s) for s in list_stories(city_id=city_id, scheme_id=scheme_id)],
        "overview": content_overview(),
    }

    blocks: List[Dict[str, Any]] = []
    for spec in PORTAL_LAYOUT:
        kind = spec["kind"]
        if kind == "page":
            page = pages.get(spec["page"])
            if page:
                blocks.append({"kind": "page", "page": page})
        elif kind == "timeline":
            blocks.append({"kind": "timeline", "heading": spec.get("heading", "Our journey"),
                           "items": site["history"]})
        elif kind == "stories":
            blocks.append({"kind": "stories", "heading": spec.get("heading", "Success stories"),
                           "items": site["stories"]})
        elif kind == "contact":
            blocks.append({"kind": "contact", "heading": spec.get("heading", "Contact us"),
                           "items": site["contacts"]})
        elif kind == "stats":
            blocks.append({"kind": "stats", "heading": spec.get("heading", "Portal at a glance")})
        elif kind == "hero":
            blocks.append({"kind": "hero", "heading": spec.get("heading", CONTENT_CONFIG["site_name"]),
                           "subheading": spec.get("subheading", CONTENT_CONFIG["tagline"])})
        elif kind == "ads":
            blocks.append(ad_section(spec.get("slot", "infeed"), category=spec.get("category"),
                                     city_id=city_id, scheme_id=scheme_id, lang=lang,
                                     heading=spec.get("heading")))
    site["layout"] = blocks
    return site
