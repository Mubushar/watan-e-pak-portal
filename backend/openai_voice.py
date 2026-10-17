"""
OpenAI voice for the Arz-e-Pak assistant
========================================

Everything audio goes through OpenAI, with the API key kept on this server:

* **Live voice agent** — OpenAI Realtime API (speech-to-speech over WebRTC). The app
  asks :func:`realtime_session` for a short-lived client secret, then connects straight
  to OpenAI; the model listens, talks, can be interrupted, and calls the app's tools
  (listing search, details, the user's listings, drafting a listing).
* **Voice notes** — :func:`transcribe` (speech-to-text) and :func:`speak` (text-to-speech).

Configuration (environment variables, or ``backend/.env``)::

    OPENAI_API_KEY=sk-...                     # required
    OPENAI_REALTIME_MODEL=gpt-realtime-2.1    # live agent
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
REALTIME_MODEL = os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime-2.1")
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
    try:
        err = resp.json().get("error") or {}
        msg = err.get("message") if isinstance(err, dict) else err
    except Exception:
        msg = resp.text[:200]
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
REALTIME_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "name": "search_listings",
        "description": "Search Arz-e-Pak property listings. Use whenever the user wants to find, buy, rent or compare properties, "
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
        "description": "Get full details of one listing by its id (from search results).",
        "parameters": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"], "additionalProperties": False},
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
        "If a turn has no clear language (only a number or a place name), keep the language of their previous turn."
    ),
    "ur": "Speak only natural Pakistani Urdu, even when the user uses English words. Never switch to another language.",
    "en": "Speak only English, even when the user speaks Urdu. Never switch to another language.",
}


# Repeated last: realtime models drift into English (tool results are English) unless reminded.
_LANGUAGE_REMINDER = {
    "auto": "Always answer in the language the user used in their most recent turn: Urdu if they just spoke Urdu, English if they just spoke English.",
    "ur": "Always answer in Urdu.",
    "en": "Always answer in English.",
}


def realtime_instructions(user: Optional[Dict[str, Any]], reply_lang: str) -> str:
    name = (user or {}).get("name")
    who = f"You are talking to {name}, a {(user or {}).get('role', 'member')} on Arz-e-Pak." if user else "The user is a guest (not signed in)."
    return "\n".join([
        "# Role",
        "You are Arz-e-Pak AI, the friendly real-estate voice assistant of the Arz-e-Pak app in Pakistan. "
        "You help people find, buy, rent, sell and list property. " + who,
        "",
        "# Language",
        _LANGUAGE_POLICY.get(reply_lang, _LANGUAGE_POLICY["auto"]),
        "",
        "# Style",
        "- This is a spoken conversation: keep each turn short (1-3 sentences), warm and natural, like a helpful local agent.",
        "- Say prices in crore/lakh and sizes in marla/kanal. Never read out ids, links or long numbers digit by digit.",
        "- If the user interrupts, stop and listen.",
        "",
        "# Tools",
        "- Use search_listings whenever the user wants properties; then mention the best one to three matches "
        "(name, size, price). Never invent listings, prices or availability.",
        "- Use get_listing for details about a specific result.",
        "- Use my_listings when the user asks about their own listings. If it reports they are not signed in, tell them to sign in with a one-time code.",
        "- When the user wants to sell or rent out a property, ask briefly for anything missing (type, city, size, price), "
        "then call draft_listing and tell them to tap 'Create listing' on screen to add photos and publish.",
        "- Results also appear on screen as cards, so don't list everything aloud.",
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
    if REALTIME_MODEL.startswith("gpt-realtime-2"):
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
    }
