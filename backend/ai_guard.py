"""
Protects the OpenAI-backed endpoints from abuse (they spend the server's API credit).

* Per-caller rate limits — the caller is the signed-in user (bearer token) or, for
  guests, the client IP. Sliding windows, kept in memory.
* Optional sign-in requirement: ``AI_REQUIRE_SIGNIN=1`` turns guests away from the AI.

Settings (environment variables, or ``backend/.env``)::

    AI_REQUIRE_SIGNIN=0          # 1 = only signed-in users may use the AI
    AI_CHAT_PER_MINUTE=30        # chat completions (typed messages, voice notes)
    AI_VOICE_PER_MINUTE=30       # speech-to-text + text-to-speech calls
    AI_LIVE_PER_HOUR=6           # live voice-agent sessions started (the most expensive call)
    AI_EXTRACT_PER_MINUTE=20     # documents read for the chat (/ai/extract — server CPU, no credit)
    AI_TRUST_PROXY=0             # 1 = behind a reverse proxy: identify guests by X-Forwarded-For
"""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Optional, Tuple

from fastapi import HTTPException, Request

import auth
import envfile  # noqa: F401  (loads backend/.env)

LIMITS: Dict[str, Tuple[int, int]] = {
    "chat": (int(os.getenv("AI_CHAT_PER_MINUTE", "30")), 60),
    "voice": (int(os.getenv("AI_VOICE_PER_MINUTE", "30")), 60),
    "live": (int(os.getenv("AI_LIVE_PER_HOUR", "6")), 3600),
    "extract": (int(os.getenv("AI_EXTRACT_PER_MINUTE", "20")), 60),
}


def _flag(name: str) -> bool:
    return os.getenv(name, "0").strip().lower() in ("1", "true", "yes", "on")


REQUIRE_SIGNIN = _flag("AI_REQUIRE_SIGNIN")
TRUST_PROXY = _flag("AI_TRUST_PROXY")

_hits: Dict[Tuple[str, str], Deque[float]] = defaultdict(deque)
_lock = threading.Lock()


def _caller(request: Request) -> Tuple[str, bool]:
    """('user:<id>' | 'ip:<addr>', signed_in)."""
    header = request.headers.get("authorization") or ""
    token = header[7:].strip() if header.lower().startswith("bearer ") else header.strip()
    user = auth.current_user(token) if token else None
    if user is not None:
        return f"user:{user.id}", True
    # X-Forwarded-For can be faked by anyone, so only trust it behind your own proxy.
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() if TRUST_PROXY else ""
    return f"ip:{forwarded or (request.client.host if request.client else 'unknown')}", False


def _retry_after(key: Tuple[str, str], limit: int, window: int) -> Optional[int]:
    now = time.monotonic()
    with _lock:
        q = _hits[key]
        while q and now - q[0] >= window:
            q.popleft()
        if len(q) >= limit:
            return max(1, int(window - (now - q[0])) + 1)
        q.append(now)
    return None


def check(request: Request, bucket: str) -> None:
    """Raise 401 (sign-in required) or 429 (too many requests) for this caller."""
    who, signed_in = _caller(request)
    if REQUIRE_SIGNIN and not signed_in:
        raise HTTPException(status_code=401, detail="Please sign in to use the AI assistant.",
                            headers={"WWW-Authenticate": "Bearer"})
    limit, window = LIMITS[bucket]
    if limit <= 0:
        return
    wait = _retry_after((bucket, who), limit, window)
    if wait is not None:
        raise HTTPException(status_code=429, detail=f"Too many AI requests — please try again in {wait} seconds.",
                            headers={"Retry-After": str(wait)})


def reset() -> None:
    """Clear all counters (tests)."""
    with _lock:
        _hits.clear()
