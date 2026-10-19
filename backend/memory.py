"""
The assistant's memory, per signed-in user and private to them.

Short-term ("near") memory
    The last turns of each conversation (``turns_db``), so a follow-up like "and in Lahore?" or
    "the second one" makes sense even after a page reload or on another device. Kept for
    ``TURN_DAYS`` days, at most ``MAX_TURNS`` per user.

Long-term memory
    Facts about the user's search that stay useful across conversations (``memories_db``):
    budget, cities and schemes of interest, property type and size, bedrooms, buying or renting,
    reply language, plus anything they ask the assistant to remember ("remember I work in
    Blue Area"). Each memory has a ``key`` so a newer budget replaces the old one instead of
    piling up; free-form notes keep their own text.

Recall
    ``recall(user_id, query)`` returns the memories that matter for this question (word overlap
    plus kind and recency) and ``context()`` renders them as a short block for the model. Guests
    get no memory. A user can list, delete or clear their memories and switch memory off
    (``/me/memory``); nothing here is visible to other users or to admins.

All stores are ``*_db`` containers, so durable storage (``storage.py``) saves them with the rest.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

import knowledge

MAX_TURNS = 200
TURN_DAYS = 14
MAX_MEMORIES = 150
MAX_TEXT = 1200


class ConversationTurn(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    conversation_id: str = "default"
    role: str  # user | assistant
    content: str
    created_at: datetime = Field(default_factory=datetime.now)


class UserMemory(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    kind: str  # budget | city | scheme | property_type | size | bedrooms | purpose | language | note
    key: str   # unique per user for single-valued facts (e.g. "budget_max"); note:<hash> for notes
    value: str
    source: str = "inferred"  # inferred (from what they asked) | explicit (they asked us to remember)
    hits: int = 1
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


turns_db: List[ConversationTurn] = []
memories_db: List[UserMemory] = []
settings_db: Dict[str, Dict[str, Any]] = {}  # user_id -> {"enabled": bool}


# ---------------------------------------------------------------- settings


def enabled(user_id: Optional[str]) -> bool:
    return bool(user_id) and settings_db.get(user_id, {}).get("enabled", True)


def set_enabled(user_id: str, on: bool) -> Dict[str, Any]:
    settings_db[user_id] = {**settings_db.get(user_id, {}), "enabled": bool(on)}
    return {"enabled": bool(on)}


# ---------------------------------------------------------------- short-term


def add_turn(user_id: str, role: str, content: str, conversation_id: Optional[str] = None) -> Optional[ConversationTurn]:
    if not enabled(user_id) or role not in ("user", "assistant") or not (content or "").strip():
        return None
    turn = ConversationTurn(user_id=user_id, role=role, content=content.strip()[:MAX_TEXT],
                            conversation_id=(conversation_id or "default")[:80])
    turns_db.append(turn)
    _prune_turns(user_id)
    return turn


def _prune_turns(user_id: str) -> None:
    cutoff = datetime.now() - timedelta(days=TURN_DAYS)
    mine = [t for t in turns_db if t.user_id == user_id]
    drop = {t.id for t in mine if t.created_at < cutoff}
    keep = [t for t in mine if t.id not in drop]
    if len(keep) > MAX_TURNS:
        drop |= {t.id for t in keep[:-MAX_TURNS]}
    if drop:
        turns_db[:] = [t for t in turns_db if t.id not in drop]


def recent(user_id: str, conversation_id: Optional[str] = None, limit: int = 8) -> List[Dict[str, Any]]:
    rows = [t for t in turns_db if t.user_id == user_id and (conversation_id is None or t.conversation_id == conversation_id)]
    return [{"role": t.role, "content": t.content, "at": t.created_at.isoformat(timespec="seconds")} for t in rows[-limit:]]


# ---------------------------------------------------------------- long-term

_REMEMBER = re.compile(r"^\s*(?:please\s+)?(?:remember|note|keep in mind|yaad rakh(?:o|ein|na)?|یاد رکھ\S*)\s*(?:that|ke|کہ)?\s*[:,-]?\s*(.+)$",
                       re.IGNORECASE)


# CNIC (12345-1234567-1), card / account numbers (13-19 digits) and passwords are never kept.
_SENSITIVE = re.compile(r"\b\d{5}-?\d{7}-?\d\b|\b(?:\d[ -]?){13,19}\b|\bpass(?:word|code)\b|\bpin\b|\biban\b", re.IGNORECASE)


def _upsert(user_id: str, kind: str, key: str, value: str, source: str = "inferred") -> UserMemory:
    for m in memories_db:
        if m.user_id == user_id and m.key == key:
            if m.source == "explicit" and source == "inferred" and m.value != value and kind == "note":
                continue
            m.value, m.kind, m.updated_at, m.hits = value, kind, datetime.now(), m.hits + 1
            if source == "explicit":
                m.source = "explicit"
            return m
    mem = UserMemory(user_id=user_id, kind=kind, key=key, value=value, source=source)
    memories_db.append(mem)
    mine = [x for x in memories_db if x.user_id == user_id]
    if len(mine) > MAX_MEMORIES:  # forget the least useful inferred ones first
        victims = sorted((x for x in mine if x.source == "inferred"), key=lambda x: (x.hits, x.updated_at))
        gone = {x.id for x in victims[: len(mine) - MAX_MEMORIES]}
        memories_db[:] = [x for x in memories_db if x.id not in gone]
    return mem


def _places(text: str) -> Dict[str, List[str]]:
    """Cities and housing schemes named in the text (matched against the portal's base data)."""
    import server as core

    low = " " + knowledge.normalize(text) + " "
    found: Dict[str, List[str]] = {"city": [], "scheme": []}
    for c in core.cities_db:
        names = [c.name] + ([c.name_ur] if c.name_ur else [])
        if any(f" {knowledge.normalize(n)} " in low or f" {knowledge.normalize(n)}," in low for n in names if n):
            found["city"].append(c.name)
    for s in core.housing_schemes_db:
        if len(s.name) > 4 and knowledge.normalize(s.name) in low:
            found["scheme"].append(s.name)
    return found


def _money(v: float) -> str:
    return f"{v / 1e7:.2f} crore" if v >= 1e7 else f"{v / 1e5:.0f} lakh"


def learn(user_id: str, text: str) -> List[Dict[str, Any]]:
    """Remember what a user message says about their search. Returns what was stored."""
    if not enabled(user_id) or not (text or "").strip():
        return []
    stored: List[UserMemory] = []
    m = _REMEMBER.match(text.strip())
    if m and len(m.group(1).strip()) > 3 and not _SENSITIVE.search(m.group(1)):
        note = re.split(r"(?<=[.!?۔])\s+|\n", m.group(1).strip())[0].rstrip(".")[:300]
        stored.append(_upsert(user_id, "note", "note:" + knowledge.normalize(note)[:60], note, source="explicit"))
    f = knowledge.parse_query(text)
    if f.get("max_price"):
        stored.append(_upsert(user_id, "budget", "budget_max", _money(f.get("budget") or f["max_price"])))
    if f.get("min_price"):
        stored.append(_upsert(user_id, "budget", "budget_min", _money(f["min_price"])))
    if f.get("marla"):
        stored.append(_upsert(user_id, "size", "size", f"{f['marla']:g} marla" if f["marla"] < 20 else f"{f['marla'] / 20:g} kanal"))
    if f.get("bedrooms"):
        stored.append(_upsert(user_id, "bedrooms", "bedrooms", f"{f['bedrooms']} bedrooms"))
    # "near my office" / "my shop is in Saddar" describe the user, not what they want to buy.
    if f.get("category") and not re.search(r"\b(?:my|our|mera|meri|hamara)\s+(?:own\s+)?" + f["category"], text, re.IGNORECASE):
        stored.append(_upsert(user_id, "property_type", "property_type", f["category"]))
    if f.get("purpose"):
        stored.append(_upsert(user_id, "purpose", "purpose", "renting" if f["purpose"] == "rent" else "buying"))
    places = _places(text)
    for name in places["city"][:3]:
        stored.append(_upsert(user_id, "city", "city:" + name.lower(), name))
    for name in places["scheme"][:3]:
        stored.append(_upsert(user_id, "scheme", "scheme:" + name.lower(), name))
    if re.search(r"[؀-ۿ]", text):
        stored.append(_upsert(user_id, "language", "language", "Urdu (Urdu script)"))
    return [{"kind": s.kind, "value": s.value} for s in stored]


def remember(user_id: str, note: str) -> Dict[str, Any]:
    note = (note or "").strip()[:300]
    if not note:
        return {"error": "Nothing to remember"}
    if _SENSITIVE.search(note):
        return {"error": "That looks like an ID, card number or password; it isn't stored."}
    if not enabled(user_id):
        return {"error": "Memory is switched off for this account"}
    m = _upsert(user_id, "note", "note:" + knowledge.normalize(note)[:60], note, source="explicit")
    return {"remembered": True, "id": m.id, "value": m.value}


def forget(user_id: str, memory_id: Optional[str] = None) -> Dict[str, Any]:
    before = len(memories_db)
    if memory_id:
        memories_db[:] = [m for m in memories_db if not (m.user_id == user_id and m.id == memory_id)]
    else:
        memories_db[:] = [m for m in memories_db if m.user_id != user_id]
        turns_db[:] = [t for t in turns_db if t.user_id != user_id]
    return {"forgotten": before - len(memories_db)}


def list_for(user_id: str) -> Dict[str, Any]:
    mine = sorted((m for m in memories_db if m.user_id == user_id), key=lambda m: m.updated_at, reverse=True)
    return {"enabled": enabled(user_id) if user_id else False,
            "memories": [m.model_dump(mode="json", exclude={"user_id"}) for m in mine],
            "recent_turns": len([t for t in turns_db if t.user_id == user_id])}


KIND_WEIGHT = {"note": 1.3, "budget": 1.2, "city": 1.1, "scheme": 1.1, "property_type": 1.0, "size": 1.0,
               "bedrooms": 0.9, "purpose": 0.9, "language": 0.6}
ALWAYS = {"budget", "purpose", "property_type", "language"}


def recall(user_id: str, query: str = "", limit: int = 8) -> List[Dict[str, Any]]:
    if not enabled(user_id):
        return []
    q = set(knowledge.tokens(query))
    now = datetime.now()
    scored = []
    for m in memories_db:
        if m.user_id != user_id:
            continue
        overlap = len(q & set(knowledge.tokens(m.value)))
        age_days = max(0.0, (now - m.updated_at).total_seconds() / 86400)
        recency = 1 / (1 + age_days / 30)
        score = KIND_WEIGHT.get(m.kind, 1.0) * (1 + 2 * overlap + 0.2 * min(m.hits, 5)) * recency
        if m.kind in ALWAYS or overlap or m.source == "explicit":
            scored.append((score, m))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [{"id": m.id, "kind": m.kind, "value": m.value, "source": m.source,
             "updated": m.updated_at.date().isoformat()} for _, m in scored[:limit]]


def context(user_id: Optional[str], query: str = "") -> str:
    if not user_id:
        return ""
    rows = recall(user_id, query)
    if not rows:
        return ""
    lines = [f"- {r['kind'].replace('_', ' ')}: {r['value']}" + (" (they asked me to remember)" if r["source"] == "explicit" else "")
             for r in rows]
    return ("What I remember about this user from earlier conversations (use it to tailor answers, mention it "
            "naturally, and let newer instructions win):\n" + "\n".join(lines))
