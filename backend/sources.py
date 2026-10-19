"""
How much to trust a piece of knowledge, from where it came from.

Every answer the assistant builds from the portal's knowledge (RAG) or the web carries its
sources with a trust tier, so people can see what a fact rests on and the model can prefer the
stronger source when two disagree:

``official``    a government body, regulator or development authority (CDA, RDA, LDA, KDA,
                SBP, PBS, FBR, SECP, provincial governments, DHA's own sites …)
``verified``    checked by a portal administrator
``reference``   an established reference or major news outlet (Wikipedia, Dawn, Business
                Recorder, The News …)
``listing``     a listing submitted by an owner or agent on the portal (not independently checked)
``unverified``  anything else, including sample data
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlsplit

TIERS = ["official", "verified", "reference", "listing", "unverified"]
RANK = {t: i for i, t in enumerate(TIERS)}

# Government, regulators and development authorities (federal .gov.pk, Punjab .gop.pk, Sindh
# .gos.pk, KP .gkp.pk, Balochistan .gob.pk, plus bodies on their own domains).
OFFICIAL_SUFFIXES = (".gov.pk", ".gop.pk", ".gos.pk", ".gkp.pk", ".gob.pk")
OFFICIAL_DOMAINS = {
    "sbp.org.pk", "secp.gov.pk", "nepra.org.pk", "ogra.org.pk", "ppra.org.pk", "wapda.gov.pk",
    "dhai-r.com.pk", "dhalahore.org", "dhakarachi.org",
}
REFERENCE_DOMAINS = {
    "wikipedia.org", "dawn.com", "brecorder.com", "thenews.com.pk", "tribune.com.pk", "geo.tv",
    "app.com.pk", "bbc.com", "reuters.com", "nation.com.pk", "profit.pakistantoday.com.pk",
    "worldbank.org", "adb.org", "imf.org", "openstreetmap.org", "citypopulation.de",
}


def site_of(url: Optional[str]) -> str:
    try:
        return (urlsplit(url or "").netloc or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def _matches(site: str, domains: Iterable[str]) -> bool:
    return any(site == d or site.endswith("." + d) for d in domains)


def tier_for_url(url: Optional[str]) -> str:
    site = site_of(url)
    if not site:
        return "unverified"
    if site.endswith(OFFICIAL_SUFFIXES) or _matches(site, OFFICIAL_DOMAINS):
        return "official"
    if _matches(site, REFERENCE_DOMAINS):
        return "reference"
    return "unverified"


def tier_for_sources(sources: Iterable[Any]) -> str:
    """The best tier among a record's sources (strings or {"url": …} dicts)."""
    best = "unverified"
    for s in sources or []:
        url = s.get("url") if isinstance(s, dict) else s
        t = tier_for_url(str(url or ""))
        if RANK[t] < RANK[best]:
            best = t
    return best


def best(*tiers: str) -> str:
    return min((t for t in tiers if t in RANK), key=RANK.__getitem__, default="unverified")


def describe(tier: str) -> str:
    return {
        "official": "official source (government / authority)",
        "verified": "checked by the portal",
        "reference": "reference or major news outlet",
        "listing": "listing submitted on the portal",
        "unverified": "not verified",
    }.get(tier, "not verified")


def sort_sources(sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Tag each web source with its tier and put the strongest first."""
    for s in sources:
        s.setdefault("tier", tier_for_url(s.get("url")))
    return sorted(sources, key=lambda s: RANK.get(s.get("tier", "unverified"), 9))
