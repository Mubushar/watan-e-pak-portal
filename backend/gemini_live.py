"""
Gemini Live — an optional live voice agent for testing (Google AI Studio free tier)
==================================================================================

The default live voice agent is OpenAI Realtime (``openai_voice.py``). Setting
``VOICE_PROVIDER=gemini`` switches the app's *live conversation* to Google's Gemini Live
API instead; voice notes and chat are unaffected. Going back is deleting that line.

The app never sees the API key: :func:`live_session` mints a short-lived, single-use
ephemeral token (``POST /v1beta/auth_tokens``) and returns it with the WebSocket URL and
the session setup (instructions, voice, the same tools as the OpenAI agent). The app then
streams 16 kHz PCM up and plays 24 kHz PCM down (``portable/src/lib/gemini-live.ts``).

Configuration (environment variables, or ``backend/.env``)::

    VOICE_PROVIDER=gemini                 # openai (default) | gemini
    GEMINI_API_KEY=...                    # from https://aistudio.google.com/apikey
    GEMINI_LIVE_MODEL=gemini-3.8-live     # Live model id
    GEMINI_VOICE=Kore                     # prebuilt voice name

Free-tier content may be used by Google to improve its products, so test with demo data.
"""

from __future__ import annotations

import copy
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

import envfile  # noqa: F401  (loads backend/.env)
import openai_voice

API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
MODEL = os.getenv("GEMINI_LIVE_MODEL", "gemini-3.8-live").strip()
VOICE = os.getenv("GEMINI_VOICE", "Kore").strip()
PROVIDER = os.getenv("VOICE_PROVIDER", "openai").strip().lower()

API_BASE = "https://generativelanguage.googleapis.com/v1beta"
WS_URL = ("wss://generativelanguage.googleapis.com/ws/"
          "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContentConstrained")


class GeminiError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def configured() -> bool:
    return bool(API_KEY)


def active() -> bool:
    """Is Gemini the live voice provider?"""
    return PROVIDER == "gemini" and configured()


def status() -> Dict[str, Any]:
    return {"provider": "gemini" if active() else None, "model": MODEL if active() else None,
            "voice": VOICE if active() else None}


# ------------------------------------------------------------------ tools


def _schema(s: Any) -> Any:
    """JSON Schema (OpenAI tools) -> the OpenAPI subset Gemini function declarations accept."""
    if isinstance(s, list):
        return [_schema(x) for x in s]
    if not isinstance(s, dict):
        return s
    out: Dict[str, Any] = {}
    for k, v in s.items():
        if k == "additionalProperties":
            continue  # not part of Gemini's schema subset
        if k == "type" and isinstance(v, str):
            out[k] = v.upper()
        elif k == "properties" and isinstance(v, dict):
            out[k] = {name: _schema(p) for name, p in v.items()}
        elif k == "items":
            out[k] = _schema(v)
        else:
            out[k] = v
    return out


def function_declarations() -> List[Dict[str, Any]]:
    decls = []
    for t in openai_voice.REALTIME_TOOLS:
        if t["name"] == "web_lookup":
            continue  # needs OpenAI; Gemini gets Google Search instead
        params = _schema(copy.deepcopy(t["parameters"]))
        decl: Dict[str, Any] = {"name": t["name"], "description": t["description"],
                                # Wait for the result before answering (3.8 Live defaults to non-blocking).
                                "behavior": "BLOCKING"}
        if params.get("properties"):
            decl["parameters"] = params
        decls.append(decl)
    return decls


def instructions(user: Optional[Dict[str, Any]], reply_lang: str) -> str:
    text = openai_voice.realtime_instructions(user, reply_lang)
    # The OpenAI agent's web_lookup tool is replaced by Gemini's built-in Google Search.
    return text.replace("use web_lookup", "use Google Search").replace("web_lookup", "Google Search")


def setup(user: Optional[Dict[str, Any]], reply_lang: str) -> Dict[str, Any]:
    """The BidiGenerateContent ``setup`` for one live conversation."""
    return {
        "model": f"models/{MODEL}",
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": VOICE}}},
        },
        "systemInstruction": {"parts": [{"text": instructions(user, reply_lang)}]},
        "tools": [{"functionDeclarations": function_declarations()}, {"googleSearch": {}}],
        # Caption hints: without them spoken Urdu can come back in Hindi script.
        "inputAudioTranscription": {"languageCodes": openai_voice.LANGUAGES},
        "outputAudioTranscription": {},
        "realtimeInputConfig": {
            "automaticActivityDetection": {"silenceDurationMs": 600},
            "activityHandling": "START_OF_ACTIVITY_INTERRUPTS",
        },
        # Audio-only sessions stop at ~15 min without this.
        "contextWindowCompression": {"slidingWindow": {}},
        "sessionResumption": {},
    }


# ------------------------------------------------------------------ session


def _iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _token(body: Dict[str, Any]) -> httpx.Response:
    with httpx.Client(timeout=30) as client:
        return client.post(f"{API_BASE}/auth_tokens", json=body,
                           headers={"x-goog-api-key": API_KEY, "Content-Type": "application/json"})


def live_session(user: Optional[Dict[str, Any]] = None, reply_lang: str = "auto") -> Dict[str, Any]:
    """Mint a single-use ephemeral token and return everything the app needs to connect."""
    if not configured():
        raise GeminiError("The Gemini voice agent needs GEMINI_API_KEY in backend/.env", 501)
    cfg = setup(user, reply_lang)
    now = datetime.now(timezone.utc)
    base = {"uses": 1, "expireTime": _iso(now + timedelta(minutes=30)),
            "newSessionExpireTime": _iso(now + timedelta(minutes=2))}
    try:
        # Lock the whole setup (instructions, tools) into the token so a leaked token can't be
        # used for anything else. If this shape is refused, fall back to an unlocked token: the
        # app sends the same setup itself.
        resp = _token({**base, "bidiGenerateContentSetup": cfg})
        locked = resp.status_code < 400
        if not locked and resp.status_code in (400, 422):
            resp = _token(base)
    except httpx.HTTPError as exc:
        raise GeminiError(f"Could not reach Gemini ({type(exc).__name__})") from exc
    if resp.status_code >= 400:
        try:
            msg = resp.json().get("error", {}).get("message") or resp.text
        except ValueError:
            msg = resp.text
        if "API key not valid" in msg or resp.status_code in (401, 403):
            raise GeminiError("GEMINI_API_KEY in backend/.env is not valid (or lacks access to the Live API).", 503)
        status = 429 if resp.status_code == 429 else 502
        raise GeminiError(f"Gemini refused the voice session ({resp.status_code}): {msg[:300]}", status)
    token = resp.json().get("name")
    if not token:
        raise GeminiError("Gemini returned no session token")
    return {"provider": "gemini", "token": token, "ws_url": WS_URL, "model": MODEL, "voice": VOICE,
            "setup": cfg, "locked": locked}
