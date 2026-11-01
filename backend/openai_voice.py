"""
OpenAI voice for the Watan-e-Pak assistant
========================================

Everything audio goes through OpenAI, with the API key kept on this server:

* **Live voice agent** — OpenAI Realtime API (speech-to-speech over WebRTC). The app
  asks :func:`realtime_session` for a short-lived client secret, then connects straight
  to OpenAI; the model listens, talks, can be interrupted, and calls the app's tools
  (listing search, details, the user's listings, drafting a listing).
* **Voice notes** — :func:`transcribe` (speech-to-text) and :func:`speak` (text-to-speech).

Configuration (environment variables, or ``backend/.env``)::

    OPENAI_API_KEY=sk-...                     # required
    OPENAI_REALTIME_MODEL=gpt-realtime-2.1-mini   # live agent (about a third of gpt-realtime-2.1's price)
    AI_LIVE_MAX_MINUTES=8                     # the app hangs up a live call after this many minutes
    OPENAI_TRANSCRIBE_MODEL=gpt-transcribe    # voice notes + live captions
    OPENAI_TTS_MODEL=gpt-4o-mini-tts          # voice-note replies
    OPENAI_VOICE=marin                        # built-in voice (marin, cedar, ...)
    OPENAI_VOICE_ID=voice_...                 # your own custom voice (overrides OPENAI_VOICE)
"""

from __future__ import annotations

import hashlib
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx

import envfile  # noqa: F401  (loads backend/.env)

API_KEY = os.getenv("OPENAI_API_KEY", "")
BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
REALTIME_MODEL = os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime-2.1-mini")
# Live calls are billed per audio token; the app ends a call after this long (0 = no limit).
LIVE_MAX_MINUTES = int(os.getenv("AI_LIVE_MAX_MINUTES", "8") or 0)
TRANSCRIBE_MODEL = os.getenv("OPENAI_TRANSCRIBE_MODEL", "gpt-transcribe")
TTS_MODEL = os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
VOICE = os.getenv("OPENAI_VOICE", "marin")
VOICE_ID = os.getenv("OPENAI_VOICE_ID", "")
SESSION_SECONDS = 600
MAX_SPEAK_CHARS = 1500

_URDU = re.compile(r"[؀-ۿ]")
# Expected spoken languages. Without this hint spoken Urdu can come back in Hindi
# (Devanagari) script, because the two sound alike.
LANGUAGES = ["ur", "en"]


def _language_fields(model: str) -> Dict[str, Any]:
    """`languages` is supported by gpt-transcribe / gpt-live-transcribe; older models take one `language`."""
    if model in ("gpt-transcribe", "gpt-live-transcribe"):
        return {"languages": LANGUAGES}
    return {}


class VoiceError(Exception):
    """An OpenAI voice call failed (bad key, quota, unsupported input, ...).

    ``status`` is the HTTP status to return to the app (429 for rate limits/quota,
    502 for other upstream problems)."""

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def configured() -> bool:
    return bool(API_KEY)


def voice_setting() -> Any:
    """The voice for TTS and Realtime: your custom voice if set, else a built-in one."""
    return {"id": VOICE_ID} if VOICE_ID else VOICE


def status() -> Dict[str, Any]:
    """What the assistant can use (no secrets)."""
    ok = configured()
    return {
        "provider": "openai" if ok else None,
        "stt": ok,
        "stt_model": TRANSCRIBE_MODEL if ok else None,
        "tts": ok,
        "tts_model": TTS_MODEL if ok else None,
        "realtime": ok,
        "realtime_model": REALTIME_MODEL if ok else None,
        "voice": (VOICE_ID or VOICE) if ok else None,
        "custom_voice": bool(VOICE_ID),
    }


def is_urdu(text: str, language: Optional[str] = None) -> bool:
    return bool(_URDU.search(text or "")) or (language or "").lower().startswith("ur")


def _headers() -> Dict[str, str]:
    if not API_KEY:
        raise VoiceError("Set OPENAI_API_KEY in backend/.env to enable voice")
    return {"Authorization": f"Bearer {API_KEY}"}


def _error(resp: httpx.Response) -> VoiceError:
    """Turn an OpenAI error response into a VoiceError with a readable message."""
    code = ""
    try:
        err = resp.json().get("error") or {}
        msg = err.get("message") if isinstance(err, dict) else err
        if isinstance(err, dict):
            code = f"{err.get('code') or ''} {err.get('type') or ''}"
    except Exception:
        msg = resp.text[:200]
    if resp.status_code == 429 and ("insufficient_quota" in code or "credit_balance" in code):
        return VoiceError("The OpenAI account has run out of credit — add credit at platform.openai.com → "
                          "Settings → Billing, then try again.", 402)
    if resp.status_code == 429:
        return VoiceError(f"OpenAI rate limit or quota reached — try again shortly. ({msg})", 429)
    if resp.status_code == 401:
        return VoiceError("OpenAI rejected the API key — check OPENAI_API_KEY in backend/.env.", 502)
    return VoiceError(f"OpenAI {resp.status_code}: {msg}", 502)


# ------------------------------------------------------------------ voice notes


def transcribe(audio: bytes, mime_type: str) -> str:
    """Speech-to-text for a recorded clip (Urdu, English or mixed)."""
    base = (mime_type or "audio/webm").split(";")[0]
    ext = {"audio/mp4": "m4a", "audio/x-m4a": "m4a", "audio/mpeg": "mp3"}.get(base, base.split("/")[-1] or "webm")
    data: Dict[str, Any] = {
        "model": TRANSCRIBE_MODEL,
        "prompt": "Pakistani real-estate conversation in Urdu and/or English. Write Urdu in Urdu script and English in English. "
                  "Common words: marla, kanal, crore, lakh, DHA, Bahria Town, plot, flat.",
    }
    langs = _language_fields(TRANSCRIBE_MODEL).get("languages")
    if langs:
        data["languages[]"] = langs
    try:
        with httpx.Client(timeout=120) as client:
            resp = client.post(f"{BASE_URL}/audio/transcriptions", data=data,
                               files={"file": (f"speech.{ext}", audio, base)}, headers=_headers())
    except httpx.HTTPError as exc:
        raise VoiceError(f"Could not reach OpenAI ({type(exc).__name__})") from exc
    if resp.status_code >= 400:
        raise _error(resp)
    return (resp.json().get("text") or "").strip()


def clean_for_speech(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[*_`#>]", "", text)
    text = re.sub(r"\s*·\s*", ", ", text)
    text = re.sub(r"\bPKR\b", "rupees", text)
    return re.sub(r"\s*\n+\s*", ". ", text).strip()[:MAX_SPEAK_CHARS]


def speak(text: str, language: Optional[str] = None) -> Tuple[bytes, str]:
    """Text-to-speech for a voice-note reply; returns (mp3 bytes, mime type)."""
    say = clean_for_speech(text)
    if not say:
        raise VoiceError("Nothing to say")
    urdu = is_urdu(say, language)
    body = {
        "model": TTS_MODEL,
        "voice": voice_setting(),
        "input": say,
        "response_format": "mp3",
        "instructions": ("Speak natural, warm Pakistani Urdu at a relaxed pace." if urdu
                         else "Speak clear, friendly English with a light Pakistani accent."),
    }
    try:
        with httpx.Client(timeout=90) as client:
            resp = client.post(f"{BASE_URL}/audio/speech", json=body, headers=_headers())
    except httpx.HTTPError as exc:
        raise VoiceError(f"Could not reach OpenAI ({type(exc).__name__})") from exc
    if resp.status_code >= 400:
        raise _error(resp)
    return resp.content, "audio/mpeg"


# ------------------------------------------------------------------ live agent (Realtime)

#: Functions the live agent can call. The app runs them (against this backend's REST
#: API, with the user's own session) and sends the results back to the model.
KIND_ENUM = ['school', 'high school', 'primary school', 'college', 'university', 'medical college', 'kindergarten', 'hospital', 'clinic', 'pharmacy', 'mosque', 'mall', 'supermarket', 'market', 'park', 'sports', 'bank', 'restaurant', 'cafe', 'transport', 'fuel', 'police', 'government']

PLAN_CATEGORIES = ["sector", "road", "plot_number", "plot_size", "park", "mosque", "education", "health", "commercial",
                   "mixed_use", "apartments", "community", "water", "gate", "fuel", "amenity", "parking", "graveyard"]

# Tools the typed chat gets on top of the live voice agent's (the apps run them via REST).
CHAT_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "name": "knowledge_search",
        "description": "Search the portal's knowledge base: housing schemes (approval status, authority, developer, "
                       "possession), cities, infrastructure mega projects (ring roads, motorways, industrial zones), "
                       "news and guides. Results carry [n] citation markers and a trust level; cite them.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "The question, in the user's words"},
            "types": {"type": "array", "items": {"type": "string", "enum": ["scheme", "city", "mega_project", "property",
                                                                              "news", "guide", "big_project"]}}},
            "required": ["query"]},
    },
    {
        "type": "function",
        "name": "remember",
        "description": "Remember a fact the signed-in user asks you to keep for later conversations (budget, where they "
                       "work, family needs). Never store passwords, CNIC, card or bank numbers.",
        "parameters": {"type": "object", "properties": {"note": {"type": "string"}}, "required": ["note"]},
    },
]

REALTIME_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "name": "search_listings",
        "description": "Search Watan-e-Pak property listings. Use whenever the user wants to find, buy, rent or compare properties, "
                       "including follow-ups that refine the previous search: keep the earlier city, type and budget unless the user "
                       "changes them (e.g. after 'houses in Rawalpindi under 5 crore', 'bigger than 7.5' means min_marla 7.5 with the same "
                       "city and budget). Prices are in Pakistani rupees (1 crore = 10,000,000; 1 lakh = 100,000). Size in marla "
                       "(1 kanal = 20 marla). If nothing matches, relax one filter and search again before answering.",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City in English, e.g. Lahore, Karachi, Islamabad, Rawalpindi"},
                "category": {"type": "string", "enum": ["house", "apartment", "plot", "shop", "office", "floor", "building"]},
                "use_type": {"type": "string", "enum": ["residential", "commercial"]},
                "min_price": {"type": "number", "description": "Minimum price in rupees"},
                "max_price": {"type": "number", "description": "Maximum price in rupees"},
                "bedrooms": {"type": "integer", "description": "Minimum bedrooms"},
                "min_bathrooms": {"type": "integer", "description": "Minimum bathrooms"},
                "feature": {"type": "string", "description": "A feature of the property itself, in English, e.g. solar, "
                            "basement, pool, lawn, corner, parking, gated community, sea view"},
                "near": {"type": "string", "enum": ["school", "mosque", "hospital", "mall", "market", "park", "bank",
                                                    "restaurant", "transport", "fuel"],
                         "description": "Only listings with this kind of place nearby, e.g. 'school ke paas' -> school, "
                                        "'masjid ke qareeb' -> mosque, 'near the mall' -> mall. Each result then says "
                                        "which place it is and how far."},
                "near_km": {"type": "number", "description": "How close the place must be, in km (default 2)"},
                "near_place": {"type": "string", "description": "Only listings around a NAMED place or area, e.g. "
                               "'Rawalpindi Medical University', 'Centaurus Mall', 'G-13 Islamabad' (radius near_km). "
                               "If none are that close, the result lists the nearest listings outside the radius."},
                "min_marla": {"type": "number"},
                "max_marla": {"type": "number"},
                "featured": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_listing",
        "description": "Show one listing to the user and get its full details: features (amenities) and nearby places "
                       "(closest school, mosque, hospital, mall, park, transport…) with distances. Puts the listing's card on the user's "
                       "screen with 'Open listing' and 'Request a call' buttons. Call it whenever the user wants to see, open "
                       "or share a listing, and for the listing you recommend, so its card is the one on screen.",
        "parameters": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"], "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "request_call",
        "description": "Ask the listing's owner / agent to call the user back, to arrange a visit, meet the owner or talk to "
                       "a human agent. Only call it after the user has agreed. Sends the request with the user's name and "
                       "phone/e-mail from their account; if they are not signed in, a 'Request a call' button is shown instead.",
        "parameters": {
            "type": "object",
            "properties": {
                "listing_id": {"type": "string"},
                "preferred_time": {"type": "string", "description": "When the user would like the call or visit, if they said, in English. "
                                   "Urdu days: پیر Monday, منگل Tuesday, بدھ Wednesday, جمعرات Thursday, جمعہ Friday, "
                                   "ہفتہ / ہفتے Saturday, اتوار Sunday."},
                "message": {"type": "string", "description": "Anything the user wants the owner/agent to know, in English"},
            },
            "required": ["listing_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "find_places",
        "description": "Find and count real places (from the map: OpenStreetMap) inside an area — a society, phase, sector "
                       "or neighbourhood — or around a named place. Examples: 'which malls are in Bahria Phase 8 Rawalpindi' "
                       "-> kind mall, area 'Bahria Town Phase 8 Rawalpindi'; 'how many high schools are in DHA 2 Islamabad' "
                       "-> kind 'high school', area 'DHA Phase 2 Islamabad'; 'hospitals near Centaurus' -> kind hospital, "
                       "near 'Centaurus Mall'. Returns the count and names.",
        "parameters": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": KIND_ENUM},
                "area": {"type": "string", "description": "Area name with the city, e.g. 'Bahria Town Phase 8 Rawalpindi', 'G-13 Islamabad'"},
                "near": {"type": "string", "description": "A named place to search around (instead of area)"},
                "radius_km": {"type": "number", "description": "Radius around 'near', default 2"},
                "name": {"type": "string", "description": "Words the place's name must contain"},
            },
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "area_info",
        "description": "Everything about a society, phase, sector or neighbourhood: estimated population and density, size, "
                       "development level, counts of schools / mosques / hospitals / malls / parks, notable places, listings "
                       "on the portal with average prices, the portal's own development details (developer, approval, "
                       "possession, utilities) when it has them, and nearby housing areas with their population.",
        "parameters": {
            "type": "object",
            "properties": {"area": {"type": "string", "description": "Area name with the city, e.g. 'DHA Phase 2 Islamabad'"}},
            "required": ["area"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "master_plan",
        "description": "Read the official DHA master plans (Phase I, II, III, V, VI, ME-1 & ME-2, River View North / South; "
                       "georeferenced, about 10-20 m accuracy). action 'summary': a phase's plot sizes, sectors / blocks, "
                       "named roads, mosques, parks, schools, commercial areas, clubs, gates, area statement and web facts. "
                       "action 'search': find text on the plans (a block like 'C10', a road like 'Jinnah Blvd', 'masjid', "
                       "a plot number with its street). action 'at': what the plan shows around a listing or place "
                       "(roads and widths, plot sizes, parks, mosques, plot numbers).",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["summary", "search", "at"]},
                "plan": {"type": "string", "description": "e.g. 'DHA Phase II', 'DHA 5', 'River View North', 'ME-1'"},
                "query": {"type": "string", "description": "For search: the words to find"},
                "category": {"type": "string", "enum": PLAN_CATEGORIES, "description": "For search: only this kind of label"},
                "place": {"type": "string", "description": "For at: a place, a label on the plan or an area"},
                "listing_id": {"type": "string", "description": "For at: a listing id"},
                "radius_m": {"type": "number", "description": "For at: metres around the point, default 200"},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "show_plan",
        "description": "Show part of a DHA master plan in the chat: a readable close-up image of the plan around a listing, "
                       "a label on the plan (e.g. 'C10 commercial', 'Paradise Park') or a place, plus a map with the plan "
                       "laid over it. Use whenever the user wants to see the master plan, a block, the plots around a "
                       "listing, or 'share the map / plan'. Never say you can't show the plan.",
        "parameters": {
            "type": "object",
            "properties": {
                "plan": {"type": "string", "description": "Which phase, e.g. 'DHA Phase II'"},
                "place": {"type": "string", "description": "What to centre on: a label on the plan or a place"},
                "listing_id": {"type": "string"},
                "radius_m": {"type": "number", "description": "Half-width of the close-up in metres (default 250; 600+ for a whole sector)"},
            },
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "show_map",
        "description": "Put a map in the chat: a listing (or a named place / area) with the nearest schools, mosques, parks, "
                       "malls, hospitals … as markers, plus an 'Open in Google Maps' button. Use it whenever the user wants "
                       "to see something on a map, a map screenshot, or where a listing is compared with schools, mosques "
                       "and so on. Never say you can't show a map.",
        "parameters": {
            "type": "object",
            "properties": {
                "listing_id": {"type": "string", "description": "A listing id from search_listings / get_listing"},
                "place": {"type": "string", "description": "Or a named place / area, e.g. 'Rawalpindi Medical University'"},
                "kinds": {"type": "array", "items": {"type": "string", "enum": KIND_ENUM},
                          "description": "What to mark (default: school, mosque, park, mall, hospital)"},
                "radius_km": {"type": "number", "description": "How far around to look, default 2"},
            },
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "web_lookup",
        "description": "Search the web for facts the other tools don't have: a society's approval status (RDA, CDA, LDA, KDA), "
                       "development or possession progress, its developer, recent news, rules, or a place the map doesn't "
                       "know. Takes about 10 seconds, so tell the user you are checking. Mention the source website.",
        "parameters": {
            "type": "object",
            "properties": {"question": {"type": "string", "description": "A specific question in English, with the area and city"}},
            "required": ["question"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "my_listings",
        "description": "The signed-in user's own listings (to review, count or check their status).",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "draft_listing",
        "description": "Prepare a new listing the user wants to sell or rent out. Ask briefly for missing essentials "
                       "(type, city, size, price) first. The app then shows a 'Create listing' button with these details filled in.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short English title, e.g. '10 Marla House in DHA Lahore'"},
                "category": {"type": "string", "enum": ["house", "apartment", "plot", "shop", "office", "floor", "building"]},
                "use_type": {"type": "string", "enum": ["residential", "commercial"]},
                "city": {"type": "string"},
                "marla": {"type": "number", "description": "Size in marla (1 kanal = 20)"},
                "bedrooms": {"type": "integer"},
                "bathrooms": {"type": "integer"},
                "price": {"type": "number", "description": "Asking price in rupees"},
                "description": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
]

_LANGUAGE_POLICY = {
    "auto": (
        "Mirror the user's language turn by turn. Every reply is in the language of the user's LATEST turn: "
        "Urdu (or Urdu mixed with English words) -> natural Pakistani Urdu; English -> English. "
        "The moment the user switches language, switch with them, even if your earlier replies were in the other "
        "language. Listing titles and tool results are in English; still answer in the user's language. "
        "If a turn has no clear language (only a number or a place name), keep the language of their previous turn. "
        "Your words are also shown on screen as captions, so speak Urdu as Urdu script (اردو), never Roman Urdu."
    ),
    "ur": "Speak only natural Pakistani Urdu, even when the user uses English words. Never switch to another language. "
          "Your words are also shown on screen as captions, so use Urdu script (اردو), never Roman Urdu.",
    "en": "Speak only English, even when the user speaks Urdu. Never switch to another language.",
}


# Repeated last: realtime models drift into English (tool results are English) unless reminded.
_LANGUAGE_REMINDER = {
    "auto": "Always answer in the language the user used in their most recent turn: Urdu (in Urdu script) if they just spoke Urdu, English if they just spoke English.",
    "ur": "Always answer in Urdu.",
    "en": "Always answer in English.",
}


def realtime_instructions(user: Optional[Dict[str, Any]], reply_lang: str) -> str:
    name = (user or {}).get("name")
    who = f"You are talking to {name}, a {(user or {}).get('role', 'member')} on Watan-e-Pak." if user else "The user is a guest (not signed in)."
    return "\n".join([
        "# Role",
        "You are Watan-e-Pak AI, the friendly real-estate voice assistant of the Watan-e-Pak app in Pakistan. "
        "You help people find, buy, rent, sell and list property. " + who,
        "",
        "# Language",
        _LANGUAGE_POLICY.get(reply_lang, _LANGUAGE_POLICY["auto"]),
        "",
        "# Style",
        "- This is a spoken conversation: keep each turn short (1-3 sentences), warm and natural, like a helpful local agent. "
        "When the user asks about an area, give the key numbers and names (up to about 5 sentences).",
        "- Answer every part of the user's question; if they ask three things, cover all three.",
        "- Say prices in crore/lakh and sizes in marla/kanal. Never read out ids, links or long numbers digit by digit.",
        "- If the user interrupts, stop and listen.",
        "",
        "# Tools",
        "- Use search_listings whenever the user wants properties; then mention the best one to three matches "
        "(name, size, price). Never invent listings, prices or availability.",
        "- Search results include bedrooms and bathrooms, so compare them yourself; use min_bathrooms / bedrooms "
        "filters instead of opening listings one by one.",
        "- Every listing a tool returns appears on the user's screen as a card they can tap to open. To show a listing "
        "(the one you recommend, or one the user asks to see, open or share), call get_listing: its card then appears "
        "with 'Open listing' and 'Request a call' buttons. Never say you cannot show or share a card.",
        "- 'School ke paas', 'masjid ke qareeb', 'near a mall / hospital / park': use search_listings with near (and "
        "feature for things inside the property, like solar or a pool). When describing a listing, mention its features "
        "and what is nearby (from get_listing: nearby_places, with distance or walking minutes). If nearby_places is empty, "
        "say the portal has no nearby-place data for that area yet; never invent schools, mosques or other places.",
        "- 'Room / house near <a named place>' (a university, hospital, mall, sector): search_listings with near_place "
        "and only the filters the user gave. If nothing is within range, say so and ALWAYS name the nearest listings it "
        "returns (nearest_outside_radius) with their distance, and offer to widen the search. The portal has houses, "
        "flats, portions and plots; if the user wants a single room, say so and offer the closest homes for rent.",
        "- Questions about an area — which malls / schools / hospitals are in it, how many, population, how developed, "
        "what's around it: use find_places (lists and counts) and area_info (population, development, facilities, "
        "nearby housing areas). Give real names and numbers; say counts come from the map and may miss small places; "
        "say population is an estimate.",
        "- Don't stop at 'none found'. If find_places finds none, use what it also returns: 'broader' (e.g. how many "
        "schools there are when none is named 'High School') and 'closest_outside_area' (the nearest ones just outside, "
        "with distance). For well-known facts the map may lack (a society's commercial areas, a new mall), also use "
        "web_lookup.",
        "- For DHA Islamabad-Rawalpindi phases (I, II, III, V, VI, ME-1/ME-2, River View North / South) use master_plan: "
        "summary for a phase overview, search to find blocks / roads / facilities / plot numbers (for 'where is …' questions: "
        "each hit says the street it is near), at for what the plan shows around a listing or place. Explain plot sizes (e.g. 50x90 = 1 kanal, 35x65 ≈ 10 marla, 25x45 = 5 marla), "
        "road widths, nearby parks, mosques, schools and commercial areas. Say it's from the master plan and that what is "
        "built may differ. Use web_lookup for possession, development progress, prices or news.",
        "- When the user wants to see the master plan, a block or the plots around a listing, call show_plan: a plan "
        "close-up and a map with the plan overlaid appear in the chat.",
        "- When the user wants a map, a map screenshot, or to see a listing and the schools / mosques / parks / malls "
        "around it, call show_map (with the listing's id, or a place name): a map card appears in the chat.",
        "- For approval status, possession, developer, news or anything the tools don't cover, use web_lookup and "
        "name the source website. Never guess facts.",
        "- When the user wants to visit, see the property, meet the owner or talk to a human agent, offer to send a call "
        "request; once they agree, call request_call. If it says not_signed_in, tell them to tap 'Request a call' on screen.",
        "- Use my_listings when the user asks about their own listings. If it reports they are not signed in, tell them to sign in with a one-time code.",
        "- When the user wants to sell or rent out a property, ask briefly for anything missing (type, city, size, price), "
        "then call draft_listing and tell them to tap 'Create listing' on screen to add photos and publish.",
        "- Don't read every result aloud; the cards are on screen.",
        "- You search yourself. Never ask the user to press a search button or any button you haven't been told is on screen.",
        "",
        "# Safety",
        "You give general guidance, not legal or financial advice; for documents and title checks suggest a lawyer.",
        "",
        "# Reminder",
        _LANGUAGE_REMINDER.get(reply_lang, _LANGUAGE_REMINDER["auto"]),
    ])


def realtime_session(user: Optional[Dict[str, Any]] = None, reply_lang: str = "auto") -> Dict[str, Any]:
    """Mint a short-lived client secret the app uses to open a Realtime WebRTC call."""
    session: Dict[str, Any] = {
        "type": "realtime",
        "model": REALTIME_MODEL,
        "instructions": realtime_instructions(user, reply_lang),
        "audio": {
            "input": {
                "noise_reduction": {"type": "near_field"},
                "transcription": {"model": TRANSCRIBE_MODEL, **_language_fields(TRANSCRIBE_MODEL),
                                  "prompt": "Urdu and English real-estate conversation (marla, kanal, crore, lakh)."},
                "turn_detection": {"type": "semantic_vad", "eagerness": "auto", "create_response": True, "interrupt_response": True},
            },
            "output": {"voice": voice_setting()},
        },
        "tools": REALTIME_TOOLS,
        "tool_choice": "auto",
    }
    # Full gpt-realtime-2.x models take a reasoning effort; the -mini model is a distilled
    # reasoning model whose docs don't list the setting, so it is left at its default.
    if REALTIME_MODEL.startswith("gpt-realtime-2") and "mini" not in REALTIME_MODEL:
        session["reasoning"] = {"effort": "low"}
    headers = {**_headers(), "Content-Type": "application/json"}
    if user and user.get("id"):
        headers["OpenAI-Safety-Identifier"] = hashlib.sha256(str(user["id"]).encode()).hexdigest()
    body = {"expires_after": {"anchor": "created_at", "seconds": SESSION_SECONDS}, "session": session}
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(f"{BASE_URL}/realtime/client_secrets", json=body, headers=headers)
    except httpx.HTTPError as exc:
        raise VoiceError(f"Could not reach OpenAI ({type(exc).__name__})") from exc
    if resp.status_code >= 400:
        raise _error(resp)
    data = resp.json()
    return {
        "client_secret": data.get("value"),
        "expires_at": data.get("expires_at"),
        "model": REALTIME_MODEL,
        "calls_url": f"{BASE_URL}/realtime/calls",
        "voice": VOICE_ID or VOICE,
        "max_minutes": LIVE_MAX_MINUTES or None,
    }
