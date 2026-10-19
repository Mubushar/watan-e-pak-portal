"""
Web lookup for the assistant: facts the portal's own data doesn't have (a society's
approval status, development or possession progress, recent news …), answered by an
OpenAI model with web search, with the source links.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List
from urllib.parse import urlsplit, urlunsplit

import httpx

import envfile  # noqa: F401  (loads backend/.env)
import openai_voice
import sources as trust

CACHE_SECONDS = 6 * 3600  # the same question within six hours is answered from cache
_cache: Dict[str, Any] = {}

MODEL = os.getenv("OPENAI_WEB_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-6-luna"
INSTRUCTIONS = (
    "You look up facts for a Pakistani real-estate assistant. Search the web, then answer in at most "
    "5 short sentences or bullet points, in English, with concrete facts: names, numbers, dates, the "
    "approving authority (RDA, CDA, LDA, KDA, SBCA …). Prefer official sources first (government and "
    "development-authority sites: .gov.pk, .gop.pk, .gos.pk, .gkp.pk, SBP, DHA), then established news "
    "(Dawn, Business Recorder, The News, Express Tribune); avoid property-portal adverts and social media "
    "as sole evidence. Give the date of each fact. Say when sources disagree or may be out of date. "
    "No marketing language, no advice to buy."
)


class WebLookupError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def _clean(url: str) -> str:
    """Drop tracking parameters (utm_*) from a source link."""
    parts = urlsplit(url)
    query = "&".join(q for q in parts.query.split("&") if q and not q.startswith("utm_"))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


def lookup(question: str) -> Dict[str, Any]:
    key = " ".join(question.lower().split())
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return {**hit[1], "cached": True}
    result = _lookup(question)
    if len(_cache) > 500:
        _cache.clear()
    _cache[key] = (time.time(), result)
    return result


def _lookup(question: str) -> Dict[str, Any]:
    if not openai_voice.API_KEY:
        raise WebLookupError("Web lookup needs OPENAI_API_KEY in backend/.env", 501)
    try:
        r = httpx.post(
            f"{openai_voice.BASE_URL}/responses",
            headers={"Authorization": f"Bearer {openai_voice.API_KEY}"},
            timeout=90,
            json={
                "model": MODEL,
                "instructions": INSTRUCTIONS,
                "input": question.strip()[:1000],
                "tools": [{"type": "web_search", "user_location": {"type": "approximate", "country": "PK"}}],
                "reasoning": {"effort": "low"},
                "max_output_tokens": 1200,  # a short sourced answer; also bounds the cost
            },
        )
    except httpx.HTTPError as exc:
        raise WebLookupError(f"Could not reach OpenAI ({type(exc).__name__})") from exc
    if r.status_code != 200:
        raise openai_voice._error(r)
    texts: List[str] = []
    sources: Dict[str, Dict[str, str]] = {}
    for item in r.json().get("output", []):
        if item.get("type") != "message":
            continue
        for part in item.get("content", []):
            if part.get("text"):
                texts.append(part["text"])
            for a in part.get("annotations", []):
                if a.get("type") == "url_citation" and a.get("url"):
                    url = _clean(a["url"])
                    sources.setdefault(url, {"title": a.get("title") or urlsplit(url).netloc, "url": url,
                                             "site": urlsplit(url).netloc.removeprefix("www.")})
    answer = "\n".join(texts).strip()
    if not answer:
        raise WebLookupError("The web search returned no answer")
    ranked = trust.sort_sources(list(sources.values()))[:6]
    best = ranked[0]["tier"] if ranked else "unverified"
    return {"question": question, "answer": answer, "sources": ranked, "best_source_tier": best,
            "trust": trust.describe(best), "checked_at": time.strftime("%Y-%m-%d")}
