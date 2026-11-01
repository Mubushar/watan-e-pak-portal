"""
Team Messaging & Notifications wing for the Real Estate Portal
==============================================================

An in-house **team communication system** for Watan-e-Pak — the internal workspace
the "Messaging in Portal" brief asks for: conversations that stay tied to the
properties, plans, customers and tasks the team is actually managing, with
e-mail and Telegram used as **complementary notification channels** rather than
the primary store.

What it carries
---------------
* **Conversations** — direct messages, group discussions and named channels
  (Sales, Property Verification, GIS & Mapping, Customer Support, Management,
  Announcements), plus a **property discussion** panel per property record.
* **Messages** — threading (replies), ``@mentions``, pinning, reactions, edits,
  soft deletes, a per-conversation sequence number, search and unread counts
  with optional read receipts.
* **Secure file sharing** — attachments are stored as *references* (a controlled
  storage key or source URL), never embedded in the message body, and are handed
  out through **permission-checked, expiring links** (HMAC-signed, TTL bounded,
  sensitivity-gated by membership role).
* **Actionable messages** — turn a message into a task, approval, verification
  request or follow-up, assign an owner and a deadline, optionally mirrored into
  the portal's CRM task list.
* **Notifications** — a notification **queue** with per-user, per-category
  preferences across in-app / e-mail / Telegram, quiet hours, an **outbox** the
  background worker drains, and rendered e-mail and Telegram payloads.
* **Telegram as an optional channel** — per-user opt-in linking, an inbound
  bot-update handler (``/start``, ``/stop``, ``/mute``, ``/digest``, ``/status``)
  and a safety guard that keeps confidential documents and attachments *out* of
  both Telegram and e-mail payloads (short text + an authenticated deep link
  only).
* **Roles, audit, moderation and retention** — restricted channels checked
  against the portal role, a full audit trail of important actions, access
  revocation when staff leave, message reports with moderation actions, and
  retention/deletion policies.

What it deliberately does *not* do
----------------------------------
No MCP or FastAPI code lives here: ``server.py`` exposes these functions over MCP
and ``api.py`` reuses the very same functions over REST (plus a WebSocket feed
built on the in-process broker below).  It also never processes real bytes: file
content lives in controlled object storage and this module only ever holds
references — matching the brief's "do not embed large files in chat messages".

Storage note (important)
------------------------
State is kept in **in-memory lists** so the wing runs with zero infrastructure,
exactly like the rest of the portal.  The brief is explicit that in-memory lists
must **not** be the permanent message store: every store below is written through
a thin ``_store`` seam so a PostgreSQL *messaging* schema (conversations,
memberships, messages, attachments, notifications, audit) can be swapped in
without touching the engine functions.
"""

import hashlib
import hmac
import queue
import re
import secrets
import threading
import uuid
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

# ============================================================
# CONFIGURATION
# ============================================================

MESSAGING_CONFIG: Dict[str, Any] = {
    "workspace": "Watan-e-Pak",
    "currency": "PKR",
    "message_max_length": 4000,
    "edit_window_minutes": 15,
    "attachment_max_mb": 25,
    "attachment_link_ttl_minutes": 30,
    "retention_days_default": 1095,          # 3 years
    "rate_limit_per_minute": 60,
    "rate_limit_burst": 20,
    "quiet_hours": {"start": "21:00", "end": "08:00"},
    "digest_hour": 9,
    "search_min_chars": 2,
    "read_receipts_default": True,
    "deep_link_base": "/messaging/portal",
    "telegram": {
        "enabled": True,
        "max_text": 320,
        "attach_allowed": False,             # never push documents through Telegram
        "bot_name": "ArzPakPortalBot",
        "link_code_ttl_minutes": 15,
        "urgent_priority": "high",
    },
    "email": {
        "from": "no-reply@watanepak.pk",
        "reply_to": "support@watanepak.pk",
        "digest": "instant",                 # instant | hourly | daily
        "subject_prefix": "[Watan-e-Pak]",
    },
    "disclaimer": (
        "Notifications are queued and written to the outbox by the in-process "
        "dispatcher; a production deployment runs the same queue from a "
        "background worker and hands e-mail/Telegram payloads to a provider. "
        "Telegram and e-mail payloads never carry attachments or confidential "
        "document content - only short text and an authenticated deep link."
    ),
}

CONVERSATION_KINDS = ["direct", "group", "channel", "property"]
CONVERSATION_STATUSES = ["active", "archived", "locked"]
MEMBER_ROLES = ["owner", "admin", "member", "guest"]
PRESENCE_STATES = ["online", "away", "busy", "offline"]
MESSAGE_TYPES = ["text", "system", "attachment", "action", "property_link"]
ACTION_KINDS = ["task", "approval", "verification", "request"]
ACTION_STATUSES = ["open", "in_progress", "done", "cancelled"]
ATTACHMENT_KINDS = ["pdf", "image", "cad", "spreadsheet", "document", "map", "video", "archive", "other"]
SENSITIVITY_LEVELS = ["normal", "confidential", "restricted"]
NOTIFICATION_STATES = ["queued", "sent", "read", "failed", "deferred"]
OUTBOX_CHANNELS = ["in_app", "email", "telegram"]
MODERATION_ACTIONS = ["dismiss", "delete_message", "mute_author", "escalate"]
REPORT_REASONS = ["spam", "abuse", "confidential_leak", "off_topic", "other"]

# Roles that may see restricted channels / restricted attachments.
ADMIN_ROLES = ["owner", "super_admin", "admin", "manager", "management", "director", "principal"]


# Default team channels (the brief names Sales, Property Verification,
# GIS & Mapping, Customer Support and Management).
DEFAULT_CHANNELS: List[Dict[str, Any]] = [
    {"key": "sales", "name": "Sales", "purpose": "Listings, enquiries and deal coordination",
     "restricted": False, "roles": []},
    {"key": "property_verification", "name": "Property Verification",
     "purpose": "Title, document and site verification", "restricted": False, "roles": []},
    {"key": "gis_mapping", "name": "GIS & Mapping",
     "purpose": "Maps, georeferencing and spatial analysis", "restricted": False, "roles": []},
    {"key": "customer_support", "name": "Customer Support",
     "purpose": "Client queries and after-sales follow-up", "restricted": False, "roles": []},
    {"key": "management", "name": "Management",
     "purpose": "Approvals, finance and policy", "restricted": True, "roles": ADMIN_ROLES},
    {"key": "announcements", "name": "Announcements",
     "purpose": "Company-wide notices", "restricted": False, "roles": []},
]


# Notification categories with their default delivery channels and urgency.
NOTIFICATION_CATEGORIES: Dict[str, Dict[str, Any]] = {
    "mention": {"label": "Mentions", "channels": ["in_app", "email", "telegram"], "urgent": True},
    "direct": {"label": "Direct messages", "channels": ["in_app", "email", "telegram"], "urgent": True},
    "channel": {"label": "Channel messages", "channels": ["in_app"], "urgent": False},
    "property": {"label": "Property discussions", "channels": ["in_app", "email"], "urgent": False},
    "lead": {"label": "New leads", "channels": ["in_app", "email", "telegram"], "urgent": True},
    "approval": {"label": "Approvals", "channels": ["in_app", "email", "telegram"], "urgent": True},
    "task": {"label": "Task updates", "channels": ["in_app", "email"], "urgent": False},
    "system": {"label": "System notices", "channels": ["in_app"], "urgent": False},
}


# Attachment kinds: accepted extensions and whether the kind counts as sensitive
# by default (drives the sensitivity gate on expiring links).
ATTACHMENT_RULES: Dict[str, Dict[str, Any]] = {
    "pdf": {"ext": ["pdf"], "mime": "application/pdf", "sensitive": True},
    "image": {"ext": ["jpg", "jpeg", "png", "webp", "gif"], "mime": "image/*", "sensitive": False},
    "cad": {"ext": ["dwg", "dxf", "dgn"], "mime": "image/vnd.dwg", "sensitive": True},
    "spreadsheet": {"ext": ["xls", "xlsx", "csv", "ods"], "mime": "application/vnd.ms-excel", "sensitive": True},
    "document": {"ext": ["doc", "docx", "txt", "md", "rtf"], "mime": "application/msword", "sensitive": False},
    "map": {"ext": ["geojson", "kml", "kmz", "shp", "tif", "tiff"], "mime": "application/geo+json", "sensitive": True},
    "video": {"ext": ["mp4", "mov", "webm"], "mime": "video/mp4", "sensitive": False},
    "archive": {"ext": ["zip", "rar", "7z", "tar", "gz"], "mime": "application/zip", "sensitive": True},
    "other": {"ext": [], "mime": "application/octet-stream", "sensitive": False},
}

# Words the rules-based summariser / action extractor treats as signal.
TOPIC_LEXICON: Dict[str, List[str]] = {
    "price": ["price", "rate", "amount", "cost", "budget", "payment", "invoice"],
    "approval": ["approve", "approval", "sign", "signoff", "authorise", "authorize", "sanction"],
    "verification": ["verify", "verification", "title", "registry", "mutation", "fard", "due diligence"],
    "mapping": ["map", "gis", "georeference", "coordinate", "survey", "boundary", "layer"],
    "client": ["client", "customer", "buyer", "seller", "enquiry", "inquiry", "lead"],
    "deadline": ["deadline", "due", "urgent", "asap", "today", "tomorrow", "eod", "eow"],
    "design": ["plan", "drawing", "cad", "design", "layout", "elevation"],
    "legal": ["legal", "court", "litigation", "notice", "noc", "permission"],
    "construction": ["construction", "contractor", "material", "site", "labour", "labor", "steel", "cement"],
}

ACTION_PATTERNS: List[str] = [
    r"\bplease\b", r"\bneed(?:ed|s)? to\b", r"\baction\s*(?:item)?\b", r"\bfollow[\s-]?up\b",
    r"\bassign(?:ed|ment)?\b", r"\bdeadline\b", r"\bby (?:mon|tue|wed|thu|fri|sat|sun)",
    r"\bbefore\b", r"\bconfirm\b", r"\barrange\b", r"\bsend\b", r"\bschedule\b",
    r"\bapprove\b", r"\bverify\b", r"\bprepare\b", r"\breview\b", r"\bcomplete\b",
    r"\?$",
]

_MENTION_RE = re.compile(r"@([A-Za-z0-9_.\-]{2,40})")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]{2,}")
_STOPWORDS = {
    "the", "and", "for", "that", "with", "this", "from", "have", "has", "was", "were",
    "are", "you", "your", "our", "but", "not", "can", "will", "would", "should", "could",
    "there", "here", "what", "when", "which", "who", "how", "why", "all", "any", "some",
    "his", "her", "its", "their", "them", "they", "she", "him", "been", "being", "about",
    "into", "over", "under", "than", "then", "also", "just", "only", "very", "more", "most",
    "please", "thanks", "thank", "okay", "ok", "yes", "let", "get", "got", "one", "two",
}

# ============================================================
# STORES  (in-memory now; swap for PostgreSQL via the _store seam)
# ============================================================

profiles_db: List["MsgProfile"] = []
conversations_db: List["Conversation"] = []
memberships_db: List["Membership"] = []
messages_db: List["Message"] = []
attachments_db: List["Attachment"] = []
actions_db: List["MessageAction"] = []
notifications_db: List["NotificationRecord"] = []
outbox_db: List["OutboxItem"] = []
telegram_db: List["TelegramLink"] = []
audit_db: List["AuditEvent"] = []
reports_db: List["MessageReport"] = []
link_codes_db: Dict[str, Dict[str, Any]] = {}
rate_db: Dict[str, List[float]] = {}

muted_authors_db: Dict[str, Dict[str, Any]] = {}

_ATTACHMENT_SECRET = secrets.token_bytes(32)
_LOCK = threading.RLock()

# ---- In-process broker for the WebSocket feed (conversation -> subscriber queues)
_broker: Dict[str, List["queue.Queue[Dict[str, Any]]"]] = {}


def subscribe(conversation_id: str) -> "queue.Queue[Dict[str, Any]]":
    """Register a live listener for a conversation's events (WebSocket feed)."""
    q: "queue.Queue[Dict[str, Any]]" = queue.Queue()
    with _LOCK:
        _broker.setdefault(conversation_id, []).append(q)
    return q


def unsubscribe(conversation_id: str, q: "queue.Queue[Dict[str, Any]]") -> None:
    """Remove a live listener registered by :func:`subscribe`."""
    with _LOCK:
        listeners = _broker.get(conversation_id, [])
        if q in listeners:
            listeners.remove(q)
        if not listeners:
            _broker.pop(conversation_id, None)


def publish(conversation_id: str, event: Dict[str, Any]) -> None:
    """Fan an event out to every live listener of a conversation."""
    with _LOCK:
        listeners = list(_broker.get(conversation_id, []))
    for q in listeners:
        try:
            q.put_nowait(event)
        except Exception:  # pragma: no cover - a full/dead queue must not break posting
            pass


# ============================================================
# MODELS
# ============================================================


class MsgProfile(BaseModel):
    """A light messaging profile for a portal user (never holds passwords)."""

    user_id: str
    display_name: str = ""
    handle: str = ""                     # @mention handle, e.g. "bilal.ahmed"
    role: str = "member"                 # portal/primary role, drives restricted access
    email: Optional[str] = None
    mobile: Optional[str] = None
    title: Optional[str] = None
    presence: str = "offline"
    last_seen: Optional[str] = None
    notification_prefs: Dict[str, List[str]] = Field(default_factory=dict)
    quiet_hours: Optional[Dict[str, str]] = None
    digest: str = "instant"
    telegram_opt_in: bool = False
    created_at: str = Field(default_factory=lambda: _now())


class Conversation(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("cnv"))
    kind: str = "group"                  # direct | group | channel | property
    title: str = ""
    topic: Optional[str] = None
    channel_key: Optional[str] = None
    property_id: Optional[str] = None
    status: str = "active"               # active | archived | locked
    restricted: bool = False
    roles_allowed: List[str] = Field(default_factory=list)
    retention_days: int = MESSAGING_CONFIG["retention_days_default"]
    read_receipts: bool = True
    created_by: Optional[str] = None
    created_at: str = Field(default_factory=lambda: _now())
    updated_at: str = Field(default_factory=lambda: _now())
    last_message_at: Optional[str] = None
    last_seq: int = 0
    message_count: int = 0
    pinned_message_ids: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Membership(BaseModel):
    conversation_id: str
    user_id: str
    role: str = "member"                 # owner | admin | member | guest
    joined_at: str = Field(default_factory=lambda: _now())
    left_at: Optional[str] = None
    last_read_seq: int = 0
    muted: bool = False
    pinned: bool = False
    notification_level: str = "all"      # all | mentions | none


class Message(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("msg"))
    conversation_id: str
    seq: int = 0
    author_id: Optional[str] = None
    author_name: str = ""
    body: str = ""
    type: str = "text"                   # text | system | attachment | action | property_link
    parent_id: Optional[str] = None
    mentions: List[str] = Field(default_factory=list)
    attachment_ids: List[str] = Field(default_factory=list)
    action_id: Optional[str] = None
    property_id: Optional[str] = None
    pinned: bool = False
    reactions: Dict[str, List[str]] = Field(default_factory=dict)
    edited_at: Optional[str] = None
    deleted_at: Optional[str] = None
    deleted_by: Optional[str] = None
    deleted_reason: Optional[str] = None
    created_at: str = Field(default_factory=lambda: _now())


class Attachment(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("att"))
    conversation_id: str
    message_id: Optional[str] = None
    uploaded_by: Optional[str] = None
    filename: str = ""
    kind: str = "other"
    mime: Optional[str] = None
    size_bytes: int = 0
    storage_key: Optional[str] = None    # controlled object-storage key
    source_url: Optional[str] = None     # link to an existing portal record
    sensitivity: str = "normal"          # normal | confidential | restricted
    linked_type: Optional[str] = None    # property | report | plan | ...
    linked_id: Optional[str] = None
    download_count: int = 0
    created_at: str = Field(default_factory=lambda: _now())


class MessageAction(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("act"))
    conversation_id: str
    message_id: Optional[str] = None
    kind: str = "task"                   # task | approval | verification | request
    title: str = ""
    detail: Optional[str] = None
    owner_id: Optional[str] = None
    created_by: Optional[str] = None
    due_on: Optional[str] = None
    status: str = "open"                 # open | in_progress | done | cancelled
    linked_task_id: Optional[str] = None
    property_id: Optional[str] = None
    created_at: str = Field(default_factory=lambda: _now())
    completed_at: Optional[str] = None
    updates: List[Dict[str, Any]] = Field(default_factory=list)


class NotificationRecord(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("ntf"))
    user_id: str
    category: str = "system"
    title: str = ""
    body: str = ""
    conversation_id: Optional[str] = None
    message_id: Optional[str] = None
    property_id: Optional[str] = None
    actor_id: Optional[str] = None
    channels: List[str] = Field(default_factory=list)
    delivered: List[str] = Field(default_factory=list)
    status: str = "queued"               # queued | sent | read | failed | deferred
    priority: str = "normal"             # low | normal | high
    deep_link: Optional[str] = None
    created_at: str = Field(default_factory=lambda: _now())
    read_at: Optional[str] = None
    attempts: int = 0


class OutboxItem(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("out"))
    channel: str = "in_app"              # in_app | email | telegram
    notification_id: Optional[str] = None
    user_id: Optional[str] = None
    recipient: Optional[str] = None
    subject: Optional[str] = None
    body: str = ""
    payload: Dict[str, Any] = Field(default_factory=dict)
    status: str = "sent"                 # sent | failed
    provider: str = "in_process"
    created_at: str = Field(default_factory=lambda: _now())


class TelegramLink(BaseModel):
    user_id: str
    chat_id: str
    username: Optional[str] = None
    active: bool = True
    categories: List[str] = Field(default_factory=list)
    linked_at: str = Field(default_factory=lambda: _now())
    last_update_at: Optional[str] = None


class AuditEvent(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("aud"))
    at: str = Field(default_factory=lambda: _now())
    actor_id: Optional[str] = None
    action: str = ""
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    detail: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class MessageReport(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("rep"))
    message_id: str
    conversation_id: Optional[str] = None
    reporter_id: Optional[str] = None
    reason: str = "other"
    detail: Optional[str] = None
    status: str = "open"                 # open | resolved | dismissed
    resolution: Optional[str] = None
    resolved_by: Optional[str] = None
    created_at: str = Field(default_factory=lambda: _now())
    resolved_at: Optional[str] = None


# ============================================================
# HELPERS
# ============================================================


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _today() -> str:
    return date.today().isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _slug(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", ".", text)
    return text.strip(".")


def _norm_handle(handle: str) -> str:
    return _slug(_MENTION_RE.sub(r"\1", handle or ""))


def _now_dt() -> datetime:
    return datetime.now()


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _get(items: List[Any], attr: str, value: Any) -> Optional[Any]:
    for item in items:
        if isinstance(item, dict):
            if item.get(attr) == value:
                return item
        elif getattr(item, attr, None) == value:
            return item
    return None


def find_profile(user_id: Optional[str]) -> Optional[MsgProfile]:
    if not user_id:
        return None
    return _get(profiles_db, "user_id", user_id)


def ensure_profile(user_id: str, display_name: str = "", role: Optional[str] = None,
                   handle: Optional[str] = None, email: Optional[str] = None,
                   mobile: Optional[str] = None, title: Optional[str] = None) -> MsgProfile:
    """Create or update the messaging profile for a portal user.

    ``role=None`` means "leave the stored role alone" so light-touch callers
    (notifications, presence) never downgrade a real portal role to ``member``.
    """
    profile = find_profile(user_id)
    if profile is None:
        profile = MsgProfile(
            user_id=user_id, display_name=display_name or user_id, role=role or "member",
            handle=_norm_handle(handle) or _slug(display_name) or user_id,
            email=email, mobile=mobile, title=title,
        )
        profiles_db.append(profile)
    else:
        if display_name:
            profile.display_name = display_name
        if role:
            profile.role = role
        if handle:
            profile.handle = _norm_handle(handle)
        if email:
            profile.email = email
        if mobile:
            profile.mobile = mobile
        if title:
            profile.title = title
        if not profile.handle:
            profile.handle = _slug(profile.display_name) or user_id
    _ensure_prefs(profile)
    return profile


def _ensure_prefs(profile: MsgProfile) -> None:
    if not profile.notification_prefs:
        profile.notification_prefs = {
            key: list(cfg["channels"]) for key, cfg in NOTIFICATION_CATEGORIES.items()
        }
    else:
        for key, cfg in NOTIFICATION_CATEGORIES.items():
            profile.notification_prefs.setdefault(key, list(cfg["channels"]))
    if profile.quiet_hours is None:
        profile.quiet_hours = dict(MESSAGING_CONFIG["quiet_hours"])


def display_name_for(user_id: Optional[str]) -> str:
    if not user_id:
        return "System"
    profile = find_profile(user_id)
    return profile.display_name if profile and profile.display_name else user_id


def _handle_map(only: Optional[List[str]] = None) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for profile in profiles_db:
        if only is not None and profile.user_id not in only:
            continue
        if profile.handle:
            out[profile.handle.lower()] = profile.user_id
    return out


def _audit(actor_id: Optional[str], action: str, target_type: Optional[str] = None,
           target_id: Optional[str] = None, detail: Optional[str] = None,
           meta: Optional[Dict[str, Any]] = None) -> AuditEvent:
    event = AuditEvent(actor_id=actor_id, action=action, target_type=target_type,
                       target_id=target_id, detail=detail, meta=meta or {})
    audit_db.append(event)
    return event


def _rate_check(user_id: str) -> Dict[str, Any]:
    """Sliding one-minute rate limit with a burst allowance."""
    now = _now_dt().timestamp()
    window = [t for t in rate_db.get(user_id, []) if now - t < 60.0]
    limit = MESSAGING_CONFIG["rate_limit_per_minute"]
    burst = MESSAGING_CONFIG["rate_limit_burst"]
    allowed = len(window) < max(limit, burst)
    if allowed:
        window.append(now)
    rate_db[user_id] = window
    return {"allowed": allowed, "used": len(window), "limit": limit,
            "remaining": max(0, limit - len(window))}


def _max_role_rank(role: str) -> int:
    return {"guest": 1, "member": 2, "admin": 3, "owner": 4}.get(role, 2)


# ============================================================
# CATALOG  (channels, categories, attachment rules, overview)
# ============================================================


def messaging_overview() -> Dict[str, Any]:
    """Wing summary: config, channels, categories, counts and the storage note."""
    by_kind: Dict[str, int] = {}
    for conv in conversations_db:
        by_kind[conv.kind] = by_kind.get(conv.kind, 0) + 1
    return {
        "workspace": MESSAGING_CONFIG["workspace"],
        "principle": ("Keep business conversations and records inside Watan-e-Pak; "
                      "use e-mail for formal communication and Telegram for optional "
                      "alerts or quick coordination."),
        "config": MESSAGING_CONFIG,
        "conversation_kinds": CONVERSATION_KINDS,
        "member_roles": MEMBER_ROLES,
        "attachment_kinds": list(ATTACHMENT_KINDS),
        "sensitivity_levels": SENSITIVITY_LEVELS,
        "channels": DEFAULT_CHANNELS,
        "notification_categories": NOTIFICATION_CATEGORIES,
        "outbox_channels": OUTBOX_CHANNELS,
        "rollout": [
            "1. Internal messaging - direct messages, channels, property discussions, unread counts, file sharing",
            "2. E-mail notifications - invitations, mentions, assignments, approvals, important updates",
            "3. Optional Telegram bot - per-user opt-in per notification category",
            "4. Workflow automation - summarise conversations, extract action items, route leads, reminders",
        ],
        "counts": {
            "profiles": len(profiles_db), "conversations": len(conversations_db),
            "by_kind": by_kind, "memberships": len([m for m in memberships_db if not m.left_at]),
            "messages": len([m for m in messages_db if not m.deleted_at]),
            "attachments": len(attachments_db), "actions": len(actions_db),
            "notifications": len(notifications_db), "outbox": len(outbox_db),
            "telegram_links": len([t for t in telegram_db if t.active]),
            "audit_events": len(audit_db), "open_reports": len([r for r in reports_db if r.status == "open"]),
        },
        "storage_note": ("In-memory stores behind the _store seam. The brief is explicit "
                         "that these must not be the permanent message store: move to a "
                         "PostgreSQL messaging schema plus private object storage with "
                         "expiring links before production."),
        "disclaimer": MESSAGING_CONFIG["disclaimer"],
    }


def messaging_channels(channel_key: Optional[str] = None) -> Dict[str, Any]:
    """Default team channels (optionally one), each with member/live counts."""
    rows: List[Dict[str, Any]] = []
    for ch in DEFAULT_CHANNELS:
        conversations = [c for c in conversations_db if c.channel_key == ch["key"]]
        rows.append({
            **ch,
            "conversations": len(conversations),
            "members": sum(len(members_of(c.id)) for c in conversations),
            "messages": sum(c.message_count for c in conversations),
        })
    if channel_key:
        match = _get(rows, "key", channel_key)
        return {"channel": match} if match else {"error": f"unknown channel '{channel_key}'",
                                                 "channels": [r["key"] for r in rows]}
    return {"count": len(rows), "channels": rows}


def notification_categories(category: Optional[str] = None) -> Dict[str, Any]:
    """Notification categories with default channels and urgency flags."""
    rows = [{"key": key, **cfg} for key, cfg in NOTIFICATION_CATEGORIES.items()]
    if category:
        match = _get(rows, "key", category)
        return {"category": match} if match else {"error": f"unknown category '{category}'",
                                                  "categories": [r["key"] for r in rows]}
    return {"count": len(rows), "categories": rows}


def attachment_rules(kind: Optional[str] = None) -> Dict[str, Any]:
    """Accepted attachment kinds, extensions and default sensitivity."""
    rows = [{"key": key, **cfg} for key, cfg in ATTACHMENT_RULES.items()]
    if kind:
        match = _get(rows, "key", kind)
        return {"rule": match} if match else {"error": f"unknown attachment kind '{kind}'",
                                              "kinds": [r["key"] for r in rows]}
    return {"count": len(rows), "kinds": rows}


# ============================================================
# PROFILES & PRESENCE
# ============================================================


def profile_view(profile: MsgProfile) -> Dict[str, Any]:
    return {
        "user_id": profile.user_id, "display_name": profile.display_name,
        "handle": profile.handle, "role": profile.role, "title": profile.title,
        "presence": profile.presence, "last_seen": profile.last_seen,
        "digest": profile.digest, "telegram_opt_in": profile.telegram_opt_in,
        "notification_prefs": profile.notification_prefs,
        "unread": unread_counts(profile.user_id)["total"],
    }


def list_profiles(presence: Optional[str] = None, role: Optional[str] = None,
                  query: Optional[str] = None) -> Dict[str, Any]:
    """Team directory of messaging profiles."""
    rows = [p for p in profiles_db
            if (presence is None or p.presence == presence)
            and (role is None or p.role == role)]
    if query:
        needle = query.lower()
        rows = [p for p in rows
                if needle in p.display_name.lower() or needle in p.handle.lower()
                or needle in (p.email or "").lower()]
    rows.sort(key=lambda p: (p.presence != "online", p.display_name.lower()))
    return {"count": len(rows), "profiles": [profile_view(p) for p in rows]}


def set_presence(user_id: str, presence: str) -> Dict[str, Any]:
    """Set a user's presence and stamp ``last_seen``."""
    if presence not in PRESENCE_STATES:
        return {"error": f"presence must be one of {PRESENCE_STATES}"}
    profile = ensure_profile(user_id)
    profile.presence = presence
    profile.last_seen = _now()
    return {"user_id": user_id, "display_name": profile.display_name, "presence": presence,
            "last_seen": profile.last_seen}


def touch_presence(user_id: str, presence: Optional[str] = None) -> Dict[str, Any]:
    """Heartbeat: mark a user online (or a given state) without logging noise."""
    profile = ensure_profile(user_id)
    profile.presence = presence or "online"
    profile.last_seen = _now()
    return {"user_id": user_id, "presence": profile.presence, "last_seen": profile.last_seen}


# ============================================================
# ACCESS CONTROL
# ============================================================


def members_of(conversation_id: str, include_left: bool = False) -> List[Membership]:
    return [m for m in memberships_db
            if m.conversation_id == conversation_id and (include_left or not m.left_at)]


def _member(conversation_id: str, user_id: str) -> Optional[Membership]:
    for m in memberships_db:
        if m.conversation_id == conversation_id and m.user_id == user_id and not m.left_at:
            return m
    return None


def _role_allowed(conv: Conversation, role: str) -> bool:
    if not conv.roles_allowed:
        return True
    return role in conv.roles_allowed or role in ADMIN_ROLES


def can_access(conv: Conversation, user_id: Optional[str]) -> bool:
    """Membership plus role gate (restricted channels/attachments)."""
    if not user_id:
        return False
    profile = find_profile(user_id)
    role = profile.role if profile else "member"
    if conv.restricted and role not in conv.roles_allowed and role not in ADMIN_ROLES:
        return False
    member = _member(conv.id, user_id)
    if member is not None:
        return True
    # Portal admins may read public (non-restricted) channels they are not a member of.
    if not conv.restricted and role in ADMIN_ROLES and conv.kind == "channel":
        return True
    return False


def _flatten(role_or_ids: Optional[Any]) -> List[str]:
    if role_or_ids is None:
        return []
    if isinstance(role_or_ids, str):
        return [p.strip() for p in role_or_ids.split(",") if p.strip()]
    return [str(x).strip() for x in role_or_ids if str(x).strip()]


def _resolve_users(users: Optional[Any]) -> List[str]:
    """Resolve a list of user ids and/or @handles to user ids."""
    resolved: List[str] = []
    handles = _handle_map()
    for token in _flatten(users):
        if token.startswith("@"):
            token = token[1:]
        uid = handles.get(token.lower())
        if uid is None and find_profile(token):
            uid = token
        if uid is None:
            uid = token  # keep the raw id so callers can seed before the profile exists
        if uid not in resolved:
            resolved.append(uid)
    return resolved


# ============================================================
# CONVERSATIONS
# ============================================================


def _make_membership(conversation_id: str, user_id: str, role: str) -> Membership:
    member = Membership(conversation_id=conversation_id, user_id=user_id, role=role)
    memberships_db.append(member)
    return member


def _system_message(conv: Conversation, body: str) -> Message:
    return post_message(conv.id, None, body, message_type="system", _internal=True)


def create_conversation(kind: str = "group", title: str = "", created_by: Optional[str] = None,
                        participants: Optional[Any] = None, channel_key: Optional[str] = None,
                        property_id: Optional[str] = None, topic: Optional[str] = None,
                        restricted: Optional[bool] = None, roles_allowed: Optional[Any] = None,
                        retention_days: Optional[int] = None, announcement: Optional[str] = None) -> Dict[str, Any]:
    """Create a direct / group / channel / property conversation and seed members."""
    if kind not in CONVERSATION_KINDS:
        return {"error": f"kind must be one of {CONVERSATION_KINDS}"}
    member_ids = _resolve_users(participants)
    if created_by and created_by not in member_ids:
        member_ids.insert(0, created_by)

    if channel_key and kind != "channel":
        return {"error": "channel_key is only valid for kind=channel"}
    channel = _get(DEFAULT_CHANNELS, "key", channel_key) if channel_key else None
    if kind == "channel" and channel is None:
        return {"error": f"unknown channel_key '{channel_key}'",
                "channels": [c["key"] for c in DEFAULT_CHANNELS]}
    if channel:
        if restricted is None:
            restricted = channel["restricted"]
        if roles_allowed is None:
            roles_allowed = channel["roles"]
        title = title or channel["name"]
        topic = topic or channel["purpose"]

    if kind == "direct" and len(member_ids) != 2:
        return {"error": "a direct conversation needs exactly two participants"}

    conv = Conversation(
        kind=kind, title=title or ("Direct message" if kind == "direct" else "Conversation"),
        topic=topic, channel_key=channel["key"] if channel else channel_key,
        property_id=property_id, created_by=created_by,
        restricted=bool(restricted), roles_allowed=_flatten(roles_allowed),
        retention_days=retention_days or MESSAGING_CONFIG["retention_days_default"],
    )
    conversations_db.append(conv)
    for uid in member_ids:
        role = "owner" if uid == created_by and kind in ("group", "channel", "property") else "member"
        _make_membership(conv.id, uid, role)
    if announcement:
        _system_message(conv, announcement)
    _audit(created_by, "conversation.created", "conversation", conv.id,
           detail=f"{kind} '{conv.title}'", meta={"members": member_ids})
    publish(conv.id, {"event": "conversation.created", "conversation_id": conv.id})
    return {"conversation": conversation_view(conv, created_by)}


def conversation_view(conv: Conversation, user_id: Optional[str] = None) -> Dict[str, Any]:
    member = _member(conv.id, user_id) if user_id else None
    last = None
    for msg in reversed(messages_db):
        if msg.conversation_id == conv.id and not msg.deleted_at:
            last = {"id": msg.id, "author": msg.author_name, "body": msg.body,
                    "type": msg.type, "created_at": msg.created_at, "seq": msg.seq}
            break
    unread = 0
    if member:
        unread = sum(1 for m in messages_db
                     if m.conversation_id == conv.id and not m.deleted_at
                     and m.seq > member.last_read_seq and m.author_id != member.user_id)
    active_members = members_of(conv.id)
    return {
        "id": conv.id, "kind": conv.kind, "title": conv.title, "topic": conv.topic,
        "channel_key": conv.channel_key, "property_id": conv.property_id, "status": conv.status,
        "restricted": conv.restricted, "roles_allowed": conv.roles_allowed,
        "retention_days": conv.retention_days, "read_receipts": conv.read_receipts,
        "created_by": conv.created_by, "created_at": conv.created_at,
        "updated_at": conv.updated_at, "last_message_at": conv.last_message_at,
        "message_count": conv.message_count, "member_count": len(active_members),
        "members": [{"user_id": m.user_id, "name": display_name_for(m.user_id),
                     "role": m.role, "muted": m.muted} for m in active_members],
        "pinned_message_ids": conv.pinned_message_ids,
        "unread": unread, "my_role": member.role if member else None,
        "last_message": last, "metadata": conv.metadata,
    }


def list_conversations(user_id: str, kind: Optional[str] = None, include_archived: bool = False,
                       property_id: Optional[str] = None, channel_key: Optional[str] = None) -> Dict[str, Any]:
    """Conversations the user can see, newest activity first, with unread counts."""
    ensure_profile(user_id)
    rows: List[Dict[str, Any]] = []
    for conv in conversations_db:
        if kind and conv.kind != kind:
            continue
        if property_id and conv.property_id != property_id:
            continue
        if channel_key and conv.channel_key != channel_key:
            continue
        if not include_archived and conv.status == "archived":
            continue
        if not can_access(conv, user_id):
            continue
        view = conversation_view(conv, user_id)
        member = _member(conv.id, user_id)
        if member and member.muted:
            view["muted"] = True
        rows.append(view)
    rows.sort(key=lambda r: (r["last_message_at"] or r["created_at"]), reverse=True)
    total_unread = sum(r["unread"] for r in rows)
    return {"count": len(rows), "unread_total": total_unread, "conversations": rows}


def get_conversation(conversation_id: str, user_id: str) -> Dict[str, Any]:
    """One conversation with full context (members, pin, last message, links)."""
    conv = _get(conversations_db, "id", conversation_id)
    if conv is None:
        return {"error": f"conversation '{conversation_id}' not found"}
    if not can_access(conv, user_id):
        return {"error": "access denied", "conversation_id": conversation_id}
    view = conversation_view(conv, user_id)
    view["context"] = conversation_context(conversation_id, user_id)
    return {"conversation": view}


def conversation_context(conversation_id: str, user_id: Optional[str] = None) -> Dict[str, Any]:
    """Everything a conversation is tied to — property, actions, attachments, pins."""
    conv = _get(conversations_db, "id", conversation_id)
    if conv is None:
        return {}
    return {
        "property_id": conv.property_id,
        "channel_key": conv.channel_key,
        "pinned": [m.id for m in messages_db if m.conversation_id == conv.id and m.pinned],
        "open_actions": [a.id for a in actions_db
                         if a.conversation_id == conv.id and a.status in ("open", "in_progress")],
        "attachments": [a.id for a in attachments_db if a.conversation_id == conv.id],
        "unread": conversation_view(conv, user_id)["unread"] if user_id else None,
        "retention_days": conv.retention_days,
    }


def archive_conversation(conversation_id: str, user_id: str, archived: bool = True) -> Dict[str, Any]:
    conv = _get(conversations_db, "id", conversation_id)
    if conv is None:
        return {"error": f"conversation '{conversation_id}' not found"}
    if not _require_admin(conv, user_id):
        return {"error": "only an owner or admin may archive this conversation"}
    conv.status = "archived" if archived else "active"
    conv.updated_at = _now()
    _audit(user_id, "conversation.archived" if archived else "conversation.restored",
           "conversation", conv.id)
    publish(conv.id, {"event": "conversation.status", "status": conv.status})
    return {"conversation_id": conv.id, "status": conv.status}


def _require_admin(conv: Conversation, user_id: Optional[str]) -> bool:
    member = _member(conv.id, user_id) if user_id else None
    if member and _max_role_rank(member.role) >= 3:
        return True
    profile = find_profile(user_id)
    return bool(profile and profile.role in ADMIN_ROLES)


def get_or_create_direct(user_a: str, user_b: str) -> Dict[str, Any]:
    """Find (or create) the 1-to-1 conversation between two users."""
    for conv in conversations_db:
        if conv.kind != "direct":
            continue
        ids = {m.user_id for m in members_of(conv.id)}
        if ids == {user_a, user_b}:
            return {"conversation": conversation_view(conv, user_a), "created": False}
    created = create_conversation(kind="direct", created_by=user_a, participants=[user_a, user_b])
    if "error" in created:
        return created
    created["created"] = True
    return created


def get_or_create_property_thread(property_id: str, created_by: Optional[str] = None,
                                  title: Optional[str] = None) -> Dict[str, Any]:
    """Internal discussion panel for a property record."""
    for conv in conversations_db:
        if conv.kind == "property" and conv.property_id == property_id:
            return {"conversation": conversation_view(conv, created_by), "created": False}
    created = create_conversation(
        kind="property", property_id=property_id, created_by=created_by,
        participants=[created_by] if created_by else [],
        title=title or f"Property {property_id}",
        topic="Listing, documents, maps and follow-ups", announcement="Property discussion opened.",
    )
    if "error" in created:
        return created
    created["created"] = True
    return created


def add_member(conversation_id: str, user_id: str, actor_id: Optional[str] = None,
               role: str = "member") -> Dict[str, Any]:
    conv = _get(conversations_db, "id", conversation_id)
    if conv is None:
        return {"error": f"conversation '{conversation_id}' not found"}
    if actor_id and not _require_admin(conv, actor_id):
        return {"error": "only an owner or admin may add members"}
    if role not in MEMBER_ROLES:
        return {"error": f"role must be one of {MEMBER_ROLES}"}
    existing = _member(conversation_id, user_id)
    if existing:
        existing.role = role
        return {"conversation_id": conversation_id, "member": {"user_id": user_id, "role": role},
                "created": False}
    _make_membership(conversation_id, user_id, role)
    _audit(actor_id or user_id, "member.added", "conversation", conversation_id,
           detail=f"{display_name_for(user_id)} as {role}")
    publish(conversation_id, {"event": "member.added", "user_id": user_id, "role": role})
    return {"conversation_id": conversation_id, "member": {"user_id": user_id, "role": role},
            "created": True}


def update_member(conversation_id: str, user_id: str, actor_id: Optional[str] = None,
                  role: Optional[str] = None, muted: Optional[bool] = None,
                  pinned: Optional[bool] = None, notification_level: Optional[str] = None) -> Dict[str, Any]:
    member = _member(conversation_id, user_id)
    if member is None:
        return {"error": "membership not found"}
    is_self = actor_id == user_id
    if not is_self and actor_id and not _require_admin(_get(conversations_db, "id", conversation_id), actor_id):
        return {"error": "only an owner or admin may change another member's role"}
    if role:
        if role not in MEMBER_ROLES:
            return {"error": f"role must be one of {MEMBER_ROLES}"}
        member.role = role
    if muted is not None:
        member.muted = muted
    if pinned is not None:
        member.pinned = pinned
    if notification_level in ("all", "mentions", "none"):
        member.notification_level = notification_level
    return {"conversation_id": conversation_id, "member": member.model_dump()}


def remove_member(conversation_id: str, user_id: str, actor_id: Optional[str] = None,
                  reason: Optional[str] = None) -> Dict[str, Any]:
    """Remove a member (also used to revoke access when staff leave)."""
    conv = _get(conversations_db, "id", conversation_id)
    if conv is None:
        return {"error": f"conversation '{conversation_id}' not found"}
    if actor_id and actor_id != user_id and not _require_admin(conv, actor_id):
        return {"error": "only an owner or admin may remove members"}
    member = _member(conversation_id, user_id)
    if member is None:
        return {"error": "membership not found"}
    member.left_at = _now()
    _audit(actor_id or user_id, "member.removed", "conversation", conversation_id,
           detail=reason or f"{display_name_for(user_id)} removed")
    publish(conversation_id, {"event": "member.removed", "user_id": user_id})
    return {"conversation_id": conversation_id, "user_id": user_id, "removed": True, "reason": reason}


def list_members(conversation_id: str, user_id: Optional[str] = None) -> Dict[str, Any]:
    conv = _get(conversations_db, "id", conversation_id)
    if conv is None:
        return {"error": f"conversation '{conversation_id}' not found"}
    if user_id and not can_access(conv, user_id):
        return {"error": "access denied"}
    rows = []
    for m in members_of(conversation_id, include_left=True):
        profile = find_profile(m.user_id)
        rows.append({
            "user_id": m.user_id, "name": display_name_for(m.user_id), "role": m.role,
            "joined_at": m.joined_at, "left_at": m.left_at, "muted": m.muted,
            "pinned": m.pinned, "last_read_seq": m.last_read_seq,
            "presence": profile.presence if profile else "offline",
            "notification_level": m.notification_level,
        })
    return {"conversation_id": conversation_id, "count": len(rows), "members": rows}


def revoke_user_access(user_id: str, actor_id: Optional[str] = None,
                       reason: Optional[str] = None) -> Dict[str, Any]:
    """Remove a user from every conversation and unlink Telegram (staff leaving)."""
    removed: List[str] = []
    for member in memberships_db:
        if member.user_id == user_id and not member.left_at:
            member.left_at = _now()
            removed.append(member.conversation_id)
    for link in telegram_db:
        if link.user_id == user_id and link.active:
            link.active = False
    profile = find_profile(user_id)
    if profile:
        profile.presence = "offline"
    _audit(actor_id or user_id, "access.revoked", "user", user_id,
           detail=reason or "access revoked", meta={"conversations": len(removed)})
    return {"user_id": user_id, "conversations_revoked": len(removed),
            "conversation_ids": removed, "telegram_unlinked": True, "reason": reason}


# ============================================================
# MESSAGES
# ============================================================


def _parse_mentions(body: str, conversation_id: Optional[str] = None) -> List[str]:
    member_ids = None
    if conversation_id:
        member_ids = [m.user_id for m in members_of(conversation_id)]
    handles = _handle_map(member_ids)
    found: List[str] = []
    for raw in _MENTION_RE.findall(body or ""):
        uid = handles.get(raw.lower())
        if uid is None and member_ids and raw in member_ids:
            uid = raw
        if uid is None and find_profile(raw):
            uid = raw
        if uid and uid not in found:
            found.append(uid)
    return found


def message_view(msg: Message, user_id: Optional[str] = None) -> Dict[str, Any]:
    atts = [a for a in attachments_db if a.id in msg.attachment_ids]
    return {
        "id": msg.id, "conversation_id": msg.conversation_id, "seq": msg.seq,
        "author_id": msg.author_id, "author_name": msg.author_name, "body": msg.body,
        "type": msg.type, "parent_id": msg.parent_id, "mentions": msg.mentions,
        "attachment_ids": msg.attachment_ids,
        "attachments": [{"id": a.id, "filename": a.filename, "kind": a.kind,
                         "sensitivity": a.sensitivity} for a in atts],
        "action_id": msg.action_id, "property_id": msg.property_id, "pinned": msg.pinned,
        "reactions": msg.reactions, "edited_at": msg.edited_at,
        "deleted": bool(msg.deleted_at), "created_at": msg.created_at,
        "reply_count": sum(1 for m in messages_db
                           if m.parent_id == msg.id and not m.deleted_at),
        "read_by": _read_by(msg) if user_id else None,
    }


def _read_by(msg: Message) -> List[Dict[str, Any]]:
    rows = []
    for m in members_of(msg.conversation_id):
        if m.user_id == msg.author_id:
            continue
        if m.last_read_seq >= msg.seq:
            rows.append({"user_id": m.user_id, "name": display_name_for(m.user_id)})
    return rows


def post_message(conversation_id: str, author_id: Optional[str], body: str = "",
                 message_type: str = "text", parent_id: Optional[str] = None,
                 mentions: Optional[Any] = None, attachment_ids: Optional[List[str]] = None,
                 property_id: Optional[str] = None, action_id: Optional[str] = None,
                 _internal: bool = False) -> Dict[str, Any]:
    """Post a message after membership, length and rate-limit checks."""
    conv = _get(conversations_db, "id", conversation_id)
    if conv is None:
        return {"error": f"conversation '{conversation_id}' not found"}
    if conv.status == "locked":
        return {"error": "conversation is locked"}
    if not _internal:
        if not can_access(conv, author_id):
            return {"error": "access denied", "conversation_id": conversation_id}
        if len(body or "") > MESSAGING_CONFIG["message_max_length"]:
            return {"error": f"message exceeds {MESSAGING_CONFIG['message_max_length']} characters"}
        if not (body or "").strip() and not attachment_ids:
            return {"error": "message body or at least one attachment is required"}
        rate = _rate_check(author_id or "system")
        if not rate["allowed"]:
            return {"error": "rate limit exceeded", "rate": rate}
        if parent_id and _get(messages_db, "id", parent_id) is None:
            return {"error": f"parent message '{parent_id}' not found"}
    if message_type not in MESSAGE_TYPES:
        return {"error": f"type must be one of {MESSAGE_TYPES}"}

    resolved_mentions = _resolve_users(mentions) if mentions else _parse_mentions(body, conversation_id)
    if attachment_ids:
        for att_id in attachment_ids:
            att = _get(attachments_db, "id", att_id)
            if att is None:
                return {"error": f"attachment '{att_id}' not found"}

    conv.last_seq += 1
    msg = Message(
        conversation_id=conversation_id, seq=conv.last_seq, author_id=author_id,
        author_name=display_name_for(author_id), body=body or "", type=message_type,
        parent_id=parent_id, mentions=resolved_mentions,
        attachment_ids=attachment_ids or [], property_id=property_id or conv.property_id,
        action_id=action_id,
    )
    messages_db.append(msg)
    conv.message_count += 1
    conv.last_message_at = msg.created_at
    conv.updated_at = msg.created_at
    for att_id in msg.attachment_ids:
        att = _get(attachments_db, "id", att_id)
        if att and not att.message_id:
            att.message_id = msg.id

    publish(conversation_id, {"event": "message.created", "message": message_view(msg)})
    if not _internal:
        _notify_new_message(conv, msg)
        _audit(author_id, "message.posted", "message", msg.id,
               meta={"conversation_id": conversation_id})
    return {"message": message_view(msg), "conversation_id": conversation_id}


def list_messages(conversation_id: str, user_id: str, limit: int = 50,
                  before_seq: Optional[int] = None, thread_id: Optional[str] = None,
                  include_deleted: bool = False) -> Dict[str, Any]:
    """Page through a conversation's messages (oldest→newest), optionally a thread."""
    conv = _get(conversations_db, "id", conversation_id)
    if conv is None:
        return {"error": f"conversation '{conversation_id}' not found"}
    if not can_access(conv, user_id):
        return {"error": "access denied"}
    rows = [m for m in messages_db if m.conversation_id == conversation_id]
    if thread_id:
        root = _get(messages_db, "id", thread_id)
        rows = [m for m in rows if m.id == thread_id or m.parent_id == thread_id]
        if root is None:
            return {"error": f"message '{thread_id}' not found"}
    if not include_deleted:
        rows = [m for m in rows if not m.deleted_at]
    if before_seq is not None:
        rows = [m for m in rows if m.seq < before_seq]
    rows.sort(key=lambda m: m.seq)
    total = len(rows)
    if limit and limit > 0:
        rows = rows[-limit:]
    return {"conversation_id": conversation_id, "count": len(rows), "total": total,
            "messages": [message_view(m, user_id) for m in rows]}


def get_message(message_id: str, user_id: str) -> Dict[str, Any]:
    msg = _get(messages_db, "id", message_id)
    if msg is None:
        return {"error": f"message '{message_id}' not found"}
    conv = _get(conversations_db, "id", msg.conversation_id)
    if conv and not can_access(conv, user_id):
        return {"error": "access denied"}
    view = message_view(msg, user_id)
    view["thread"] = [message_view(m) for m in messages_db if m.parent_id == message_id and not m.deleted_at]
    return {"message": view}


def edit_message(message_id: str, user_id: str, body: str) -> Dict[str, Any]:
    msg = _get(messages_db, "id", message_id)
    if msg is None:
        return {"error": f"message '{message_id}' not found"}
    if msg.author_id != user_id:
        return {"error": "only the author may edit a message"}
    if msg.deleted_at:
        return {"error": "message is deleted"}
    created = _parse_iso(msg.created_at)
    if created and _now_dt() - created > timedelta(minutes=MESSAGING_CONFIG["edit_window_minutes"]):
        return {"error": f"messages can only be edited within "
                         f"{MESSAGING_CONFIG['edit_window_minutes']} minutes"}
    if len(body or "") > MESSAGING_CONFIG["message_max_length"]:
        return {"error": "message too long"}
    msg.body = body or ""
    msg.mentions = _parse_mentions(msg.body, msg.conversation_id)
    msg.edited_at = _now()
    _audit(user_id, "message.edited", "message", msg.id)
    publish(msg.conversation_id, {"event": "message.updated", "message": message_view(msg)})
    return {"message": message_view(msg)}


def delete_message(message_id: str, user_id: str, reason: Optional[str] = None) -> Dict[str, Any]:
    """Soft-delete a message (author or conversation admin)."""
    msg = _get(messages_db, "id", message_id)
    if msg is None:
        return {"error": f"message '{message_id}' not found"}
    conv = _get(conversations_db, "id", msg.conversation_id)
    if msg.author_id != user_id and not (conv and _require_admin(conv, user_id)):
        return {"error": "only the author or an admin may delete a message"}
    if msg.deleted_at:
        return {"message": message_view(msg), "already_deleted": True}
    msg.deleted_at = _now()
    msg.deleted_by = user_id
    msg.deleted_reason = reason or "user"
    if conv and msg.id in conv.pinned_message_ids:
        conv.pinned_message_ids.remove(msg.id)
    _audit(user_id, "message.deleted", "message", msg.id, detail=reason)
    publish(msg.conversation_id, {"event": "message.deleted", "message_id": msg.id})
    return {"message_id": msg.id, "deleted": True, "reason": msg.deleted_reason}


def pin_message(message_id: str, user_id: str, pinned: bool = True) -> Dict[str, Any]:
    msg = _get(messages_db, "id", message_id)
    if msg is None:
        return {"error": f"message '{message_id}' not found"}
    conv = _get(conversations_db, "id", msg.conversation_id)
    if conv is None:
        return {"error": "conversation not found"}
    if not can_access(conv, user_id):
        return {"error": "access denied"}
    msg.pinned = pinned
    if pinned and msg.id not in conv.pinned_message_ids:
        conv.pinned_message_ids.append(msg.id)
    if not pinned and msg.id in conv.pinned_message_ids:
        conv.pinned_message_ids.remove(msg.id)
    _audit(user_id, "message.pinned" if pinned else "message.unpinned", "message", msg.id)
    return {"message_id": msg.id, "pinned": pinned, "pinned_message_ids": conv.pinned_message_ids}


def react_to_message(message_id: str, user_id: str, emoji: str) -> Dict[str, Any]:
    msg = _get(messages_db, "id", message_id)
    if msg is None:
        return {"error": f"message '{message_id}' not found"}
    conv = _get(conversations_db, "id", msg.conversation_id)
    if conv and not can_access(conv, user_id):
        return {"error": "access denied"}
    emoji = (emoji or "").strip()[:8]
    if not emoji:
        return {"error": "emoji is required"}
    users = msg.reactions.setdefault(emoji, [])
    if user_id in users:
        users.remove(user_id)
    else:
        users.append(user_id)
    if not users:
        msg.reactions.pop(emoji, None)
    publish(msg.conversation_id, {"event": "message.reaction", "message_id": msg.id,
                                  "reactions": msg.reactions})
    return {"message_id": msg.id, "reactions": msg.reactions}


def thread(message_id: str, user_id: str, limit: int = 100) -> Dict[str, Any]:
    msg = _get(messages_db, "id", message_id)
    if msg is None:
        return {"error": f"message '{message_id}' not found"}
    conv = _get(conversations_db, "id", msg.conversation_id)
    if conv and not can_access(conv, user_id):
        return {"error": "access denied"}
    replies = [m for m in messages_db if m.parent_id == message_id and not m.deleted_at]
    return {"root": message_view(msg, user_id), "count": len(replies),
            "replies": [message_view(m, user_id) for m in replies]}


def search_messages(user_id: str, query: str, conversation_id: Optional[str] = None,
                    property_id: Optional[str] = None, mention: Optional[str] = None,
                    limit: int = 25) -> Dict[str, Any]:
    """Full-text-ish search across every conversation the user may access."""
    if len(query or "") < MESSAGING_CONFIG["search_min_chars"] and not mention:
        return {"error": f"query needs at least {MESSAGING_CONFIG['search_min_chars']} characters"}
    needle = (query or "").lower()
    mention_ids = _resolve_users([mention]) if mention else []
    hits: List[Dict[str, Any]] = []
    for msg in messages_db:
        if msg.deleted_at:
            continue
        conv = _get(conversations_db, "id", msg.conversation_id)
        if conv is None or not can_access(conv, user_id):
            continue
        if conversation_id and msg.conversation_id != conversation_id:
            continue
        if property_id and msg.property_id != property_id:
            continue
        if mention_ids and not any(uid in msg.mentions for uid in mention_ids):
            continue
        if needle and needle not in msg.body.lower():
            continue
        row = message_view(msg)
        row["conversation_title"] = conv.title
        hits.append(row)
    hits.sort(key=lambda r: r["created_at"], reverse=True)
    return {"query": query, "count": len(hits[:limit] if limit else hits),
            "messages": hits[:limit] if limit else hits}


def mark_read(conversation_id: str, user_id: str, up_to_seq: Optional[int] = None) -> Dict[str, Any]:
    member = _member(conversation_id, user_id)
    if member is None:
        return {"error": "membership not found"}
    conv = _get(conversations_db, "id", conversation_id)
    target = up_to_seq if up_to_seq is not None else (conv.last_seq if conv else member.last_read_seq)
    member.last_read_seq = max(member.last_read_seq, int(target))
    publish(conversation_id, {"event": "read.updated", "user_id": user_id,
                              "last_read_seq": member.last_read_seq})
    return {"conversation_id": conversation_id, "user_id": user_id,
            "last_read_seq": member.last_read_seq, "unread": unread_counts(user_id)["total"]}


def unread_counts(user_id: str) -> Dict[str, Any]:
    """Unread totals overall and per conversation for a user."""
    per: List[Dict[str, Any]] = []
    total = 0
    for member in memberships_db:
        if member.user_id != user_id or member.left_at:
            continue
        count = sum(1 for m in messages_db
                    if m.conversation_id == member.conversation_id and not m.deleted_at
                    and m.seq > member.last_read_seq and m.author_id != user_id)
        if count:
            conv = _get(conversations_db, "id", member.conversation_id)
            per.append({"conversation_id": member.conversation_id,
                        "title": conv.title if conv else member.conversation_id,
                        "unread": count, "muted": member.muted})
            total += count
    per.sort(key=lambda r: r["unread"], reverse=True)
    mentions = [m for m in messages_db
                if user_id in m.mentions and not m.deleted_at
                and m.author_id != user_id and _message_unread(user_id, m)]
    return {"user_id": user_id, "total": total, "conversations": per,
            "mentions": len(mentions), "notifications": notifications(user_id, unread_only=True)["count"]}


def _message_unread(user_id: str, msg: Message) -> bool:
    member = _member(msg.conversation_id, user_id)
    return bool(member and msg.seq > member.last_read_seq)


def read_receipts(message_id: str, user_id: str) -> Dict[str, Any]:
    msg = _get(messages_db, "id", message_id)
    if msg is None:
        return {"error": f"message '{message_id}' not found"}
    conv = _get(conversations_db, "id", msg.conversation_id)
    if conv and not can_access(conv, user_id):
        return {"error": "access denied"}
    total = len([m for m in members_of(msg.conversation_id) if m.user_id != msg.author_id])
    readers = _read_by(msg)
    return {"message_id": message_id, "read": len(readers), "of": total,
            "readers": readers, "enabled": conv.read_receipts if conv else True}


# ============================================================
# ATTACHMENTS & EXPIRING, PERMISSION-CHECKED LINKS
# ============================================================


def _infer_kind(filename: str) -> str:
    ext = (filename.rsplit(".", 1)[-1] if "." in (filename or "") else "").lower()
    for kind, rule in ATTACHMENT_RULES.items():
        if ext and ext in rule["ext"]:
            return kind
    return "other"


def attachment_view(att: Attachment) -> Dict[str, Any]:
    return {
        "id": att.id, "conversation_id": att.conversation_id, "message_id": att.message_id,
        "filename": att.filename, "kind": att.kind, "mime": att.mime,
        "size_bytes": att.size_bytes, "size_mb": round(att.size_bytes / 1048576.0, 2),
        "storage_key": att.storage_key, "source_url": att.source_url,
        "sensitivity": att.sensitivity, "linked_type": att.linked_type,
        "linked_id": att.linked_id, "uploaded_by": att.uploaded_by,
        "uploaded_by_name": display_name_for(att.uploaded_by),
        "download_count": att.download_count, "created_at": att.created_at,
        "embedded": False,   # files are references, never embedded in messages
    }


def register_attachment(conversation_id: str, uploaded_by: str, filename: str,
                        kind: Optional[str] = None, size_bytes: int = 0,
                        mime: Optional[str] = None, storage_key: Optional[str] = None,
                        source_url: Optional[str] = None, sensitivity: Optional[str] = None,
                        linked_type: Optional[str] = None, linked_id: Optional[str] = None) -> Dict[str, Any]:
    """Register a file reference (controlled storage or an existing portal record)."""
    conv = _get(conversations_db, "id", conversation_id)
    if conv is None:
        return {"error": f"conversation '{conversation_id}' not found"}
    if not can_access(conv, uploaded_by):
        return {"error": "access denied"}
    if not filename and not source_url:
        return {"error": "filename or source_url is required"}
    kind = kind or _infer_kind(filename)
    if kind not in ATTACHMENT_KINDS:
        return {"error": f"kind must be one of {ATTACHMENT_KINDS}"}
    size_mb = size_bytes / 1048576.0
    if size_mb > MESSAGING_CONFIG["attachment_max_mb"]:
        return {"error": f"file exceeds {MESSAGING_CONFIG['attachment_max_mb']} MB; "
                         f"store it in object storage and share a reference instead"}
    if sensitivity is None:
        sensitivity = "confidential" if ATTACHMENT_RULES[kind]["sensitive"] else "normal"
    if sensitivity not in SENSITIVITY_LEVELS:
        return {"error": f"sensitivity must be one of {SENSITIVITY_LEVELS}"}
    att = Attachment(
        conversation_id=conversation_id, uploaded_by=uploaded_by, filename=filename,
        kind=kind, mime=mime or ATTACHMENT_RULES[kind]["mime"], size_bytes=size_bytes,
        storage_key=storage_key or f"messaging/{conversation_id}/{uuid.uuid4().hex[:10]}-{filename}",
        source_url=source_url, sensitivity=sensitivity, linked_type=linked_type,
        linked_id=linked_id,
    )
    attachments_db.append(att)
    _audit(uploaded_by, "attachment.registered", "attachment", att.id,
           detail=f"{filename} ({sensitivity})", meta={"conversation_id": conversation_id})
    return {"attachment": attachment_view(att)}


def _attachment_access(att: Attachment, user_id: Optional[str]) -> Tuple[bool, str]:
    conv = _get(conversations_db, "id", att.conversation_id)
    if conv is None:
        return False, "conversation not found"
    if not can_access(conv, user_id):
        return False, "access denied"
    profile = find_profile(user_id)
    role = profile.role if profile else "member"
    if att.sensitivity == "restricted" and role not in ADMIN_ROLES:
        member = _member(conv.id, user_id)
        if not (member and _max_role_rank(member.role) >= 3):
            return False, "restricted file: owner/admin access only"
    return True, "ok"


def _sign(payload: str) -> str:
    return hmac.new(_ATTACHMENT_SECRET, payload.encode("utf-8"), hashlib.sha256).hexdigest()[:40]


def attachment_link(attachment_id: str, user_id: str, ttl_minutes: Optional[int] = None) -> Dict[str, Any]:
    """Mint a signed, expiring, permission-checked download link for an attachment."""
    att = _get(attachments_db, "id", attachment_id)
    if att is None:
        return {"error": f"attachment '{attachment_id}' not found"}
    ok, why = _attachment_access(att, user_id)
    if not ok:
        return {"error": why, "attachment_id": attachment_id}
    ttl = ttl_minutes or MESSAGING_CONFIG["attachment_link_ttl_minutes"]
    exp = int((_now_dt() + timedelta(minutes=ttl)).timestamp())
    payload = f"{att.id}.{user_id}.{exp}"
    token = f"{payload}.{_sign(payload)}"
    _audit(user_id, "attachment.link_issued", "attachment", att.id, detail=f"ttl={ttl}m")
    return {
        "attachment_id": att.id, "filename": att.filename, "kind": att.kind,
        "sensitivity": att.sensitivity, "storage_key": att.storage_key,
        "source_url": att.source_url, "expires_at": datetime.fromtimestamp(exp).isoformat(timespec="seconds"),
        "ttl_minutes": ttl, "token": token,
        "url": f"/messaging/attachments/{att.id}?token={token}",
        "note": "Link is signed and expires; the download endpoint re-checks membership.",
    }


def resolve_attachment_link(token: str, user_id: Optional[str] = None) -> Dict[str, Any]:
    """Verify a signed link (signature + expiry) and re-check access."""
    parts = (token or "").split(".")
    if len(parts) != 4:
        return {"valid": False, "error": "malformed token"}
    att_id, owner, exp_raw, sig = parts
    payload = f"{att_id}.{owner}.{exp_raw}"
    if not hmac.compare_digest(sig, _sign(payload)):
        return {"valid": False, "error": "signature mismatch"}
    try:
        exp = int(exp_raw)
    except ValueError:
        return {"valid": False, "error": "bad expiry"}
    if _now_dt().timestamp() > exp:
        return {"valid": False, "error": "link expired", "expired_at": datetime.fromtimestamp(exp).isoformat()}
    att = _get(attachments_db, "id", att_id)
    if att is None:
        return {"valid": False, "error": "attachment not found"}
    ok, why = _attachment_access(att, user_id or owner)
    if not ok:
        return {"valid": False, "error": why}
    att.download_count += 1
    _audit(user_id or owner, "attachment.downloaded", "attachment", att.id)
    return {"valid": True, "attachment": attachment_view(att),
            "expires_at": datetime.fromtimestamp(exp).isoformat(timespec="seconds")}


def list_attachments(conversation_id: str, user_id: str, kind: Optional[str] = None,
                     sensitivity: Optional[str] = None) -> Dict[str, Any]:
    conv = _get(conversations_db, "id", conversation_id)
    if conv is None:
        return {"error": f"conversation '{conversation_id}' not found"}
    if not can_access(conv, user_id):
        return {"error": "access denied"}
    rows = [a for a in attachments_db if a.conversation_id == conversation_id
            and (kind is None or a.kind == kind)
            and (sensitivity is None or a.sensitivity == sensitivity)]
    rows.sort(key=lambda a: a.created_at, reverse=True)
    return {"conversation_id": conversation_id, "count": len(rows),
            "attachments": [attachment_view(a) for a in rows]}


# ============================================================
# ACTIONABLE MESSAGES  (message -> task / approval / verification / request)
# ============================================================


def action_view(action: MessageAction) -> Dict[str, Any]:
    return {
        "id": action.id, "conversation_id": action.conversation_id,
        "message_id": action.message_id, "kind": action.kind, "title": action.title,
        "detail": action.detail, "owner_id": action.owner_id,
        "owner_name": display_name_for(action.owner_id) if action.owner_id else None,
        "created_by": action.created_by, "due_on": action.due_on, "status": action.status,
        "linked_task_id": action.linked_task_id, "property_id": action.property_id,
        "created_at": action.created_at, "completed_at": action.completed_at,
        "overdue": bool(action.due_on and action.status in ("open", "in_progress")
                        and action.due_on < _today()),
        "updates": action.updates,
    }


def create_action(conversation_id: str, created_by: str, title: str, kind: str = "task",
                  message_id: Optional[str] = None, detail: Optional[str] = None,
                  owner_id: Optional[str] = None, due_on: Optional[str] = None,
                  property_id: Optional[str] = None, linked_task_id: Optional[str] = None,
                  announce: bool = True) -> Dict[str, Any]:
    """Turn a message (or a whole conversation) into a tracked action item."""
    conv = _get(conversations_db, "id", conversation_id)
    if conv is None:
        return {"error": f"conversation '{conversation_id}' not found"}
    if not can_access(conv, created_by):
        return {"error": "access denied"}
    if kind not in ACTION_KINDS:
        return {"error": f"kind must be one of {ACTION_KINDS}"}
    if not (title or "").strip():
        return {"error": "title is required"}
    if message_id and _get(messages_db, "id", message_id) is None:
        return {"error": f"message '{message_id}' not found"}
    if owner_id:
        owner_id = _resolve_users([owner_id])[0]
        if not _member(conversation_id, owner_id):
            if not find_profile(owner_id):
                return {"error": f"owner '{owner_id}' is not a known user"}
    action = MessageAction(
        conversation_id=conversation_id, message_id=message_id, kind=kind, title=title,
        detail=detail, owner_id=owner_id, created_by=created_by, due_on=due_on,
        property_id=property_id or conv.property_id, linked_task_id=linked_task_id,
    )
    actions_db.append(action)
    if announce:
        post_message(
            conversation_id, created_by,
            f"[{kind}] {title}" + (f" — owner {display_name_for(owner_id)}" if owner_id else "")
            + (f", due {due_on}" if due_on else ""),
            message_type="action", action_id=action.id, _internal=True,
        )
    if owner_id and owner_id != created_by:
        queue_notification(
            owner_id, "task", title=f"New {kind} assigned",
            body=f"{display_name_for(created_by)} assigned you '{title}'"
                 + (f" (due {due_on})" if due_on else ""),
            actor_id=created_by, conversation_id=conversation_id,
            property_id=action.property_id, priority="normal",
        )
    _audit(created_by, "action.created", "action", action.id, detail=title)
    publish(conversation_id, {"event": "action.created", "action": action_view(action)})
    return {"action": action_view(action)}


def list_actions(user_id: str, conversation_id: Optional[str] = None,
                 owner_id: Optional[str] = None, status: Optional[str] = None,
                 kind: Optional[str] = None, overdue_only: bool = False) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    for action in actions_db:
        conv = _get(conversations_db, "id", action.conversation_id)
        if conv is None or not can_access(conv, user_id):
            continue
        if conversation_id and action.conversation_id != conversation_id:
            continue
        if owner_id and action.owner_id != owner_id:
            continue
        if status and action.status != status:
            continue
        if kind and action.kind != kind:
            continue
        view = action_view(action)
        if overdue_only and not view["overdue"]:
            continue
        rows.append(view)
    rows.sort(key=lambda r: (r["status"] == "done", r["due_on"] or "9999", r["created_at"]))
    by_status: Dict[str, int] = {}
    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    return {"count": len(rows), "by_status": by_status,
            "overdue": len([r for r in rows if r["overdue"]]), "actions": rows}


def get_action(action_id: str, user_id: str) -> Dict[str, Any]:
    action = _get(actions_db, "id", action_id)
    if action is None:
        return {"error": f"action '{action_id}' not found"}
    conv = _get(conversations_db, "id", action.conversation_id)
    if conv and not can_access(conv, user_id):
        return {"error": "access denied"}
    return {"action": action_view(action)}


def update_action(action_id: str, user_id: str, status: Optional[str] = None,
                  owner_id: Optional[str] = None, due_on: Optional[str] = None,
                  note: Optional[str] = None) -> Dict[str, Any]:
    action = _get(actions_db, "id", action_id)
    if action is None:
        return {"error": f"action '{action_id}' not found"}
    conv = _get(conversations_db, "id", action.conversation_id)
    if conv and not can_access(conv, user_id):
        return {"error": "access denied"}
    if status:
        if status not in ACTION_STATUSES:
            return {"error": f"status must be one of {ACTION_STATUSES}"}
        action.status = status
        if status == "done" and not action.completed_at:
            action.completed_at = _now()
    if owner_id:
        action.owner_id = _resolve_users([owner_id])[0]
    if due_on:
        action.due_on = due_on
    if note:
        action.updates.append({"at": _now(), "by": user_id, "note": note})
    _audit(user_id, "action.updated", "action", action.id, detail=status or note)
    publish(action.conversation_id, {"event": "action.updated", "action": action_view(action)})
    return {"action": action_view(action)}


def complete_action(action_id: str, user_id: str, note: Optional[str] = None) -> Dict[str, Any]:
    result = update_action(action_id, user_id, status="done", note=note)
    if "action" in result:
        action = _get(actions_db, "id", action_id)
        if action and action.created_by and action.created_by != user_id:
            queue_notification(
                action.created_by, "task", title=f"{action.kind.title()} completed",
                body=f"{display_name_for(user_id)} completed '{action.title}'",
                actor_id=user_id, conversation_id=action.conversation_id,
                priority="low",
            )
    return result


# ============================================================
# CONVERSATION INTELLIGENCE  (rules-based summary & action extraction)
# ============================================================


def _significant_terms(text: str, top: int = 8) -> List[Tuple[str, int]]:
    counts: Dict[str, int] = {}
    for word in _WORD_RE.findall((text or "").lower()):
        if word in _STOPWORDS:
            continue
        counts[word] = counts.get(word, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:top]


def summarize_conversation(conversation_id: str, user_id: str, limit: int = 80) -> Dict[str, Any]:
    """Rules-based extractive summary: participants, topics and salient lines."""
    conv = _get(conversations_db, "id", conversation_id)
    if conv is None:
        return {"error": f"conversation '{conversation_id}' not found"}
    if not can_access(conv, user_id):
        return {"error": "access denied"}
    msgs = [m for m in messages_db
            if m.conversation_id == conversation_id and not m.deleted_at and m.type != "system"]
    msgs.sort(key=lambda m: m.seq)
    window = msgs[-limit:] if limit else msgs
    combined = " ".join(m.body for m in window)
    participants: Dict[str, int] = {}
    for m in window:
        key = m.author_id or "system"
        participants[key] = participants.get(key, 0) + 1
    top_terms = _significant_terms(combined, top=10)
    topics: Dict[str, int] = {}
    low = combined.lower()
    for topic, words in TOPIC_LEXICON.items():
        hits = sum(low.count(w) for w in words)
        if hits:
            topics[topic] = hits
    topics = dict(sorted(topics.items(), key=lambda kv: -kv[1])[:5])
    scored: List[Tuple[float, Message]] = []
    term_set = {t for t, _ in top_terms[:6]}
    for m in window:
        words = set(_WORD_RE.findall(m.body.lower()))
        score = len(words & term_set) + (0.5 if "?" in m.body else 0)
        if score > 0:
            scored.append((score, m))
    scored.sort(key=lambda s: s[0], reverse=True)
    salient = [{"author": display_name_for(m.author_id), "body": m.body[:220],
                "at": m.created_at} for _, m in scored[:5]]
    return {
        "conversation_id": conversation_id, "title": conv.title, "kind": conv.kind,
        "window": len(window), "total_messages": conv.message_count,
        "participants": [{"user_id": uid, "name": display_name_for(uid), "messages": n}
                         for uid, n in sorted(participants.items(), key=lambda kv: -kv[1])],
        "topics": topics, "keywords": [{"term": t, "count": c} for t, c in top_terms],
        "salient_lines": salient,
        "open_actions": len([a for a in actions_db
                             if a.conversation_id == conversation_id and a.status in ("open", "in_progress")]),
        "method": "rules-based extractive baseline (keyword density); route to the LLM facade for prose",
    }


def extract_action_items(conversation_id: str, user_id: str, limit: int = 100,
                         create: bool = False, owner_default: Optional[str] = None) -> Dict[str, Any]:
    """Find assignment-like messages and (optionally) turn them into actions."""
    conv = _get(conversations_db, "id", conversation_id)
    if conv is None:
        return {"error": f"conversation '{conversation_id}' not found"}
    if not can_access(conv, user_id):
        return {"error": "access denied"}
    msgs = [m for m in messages_db
            if m.conversation_id == conversation_id and not m.deleted_at
            and m.type == "text"]
    msgs.sort(key=lambda m: m.seq)
    suggestions: List[Dict[str, Any]] = []
    for msg in msgs[-limit:] if limit else msgs:
        low = msg.body.lower()
        matched = [p for p in ACTION_PATTERNS if re.search(p, low)]
        if not matched:
            continue
        existing = [a for a in actions_db if a.message_id == msg.id]
        if existing:
            continue
        owner = msg.mentions[0] if msg.mentions else (owner_default or msg.author_id)
        suggestions.append({
            "message_id": msg.id, "author": display_name_for(msg.author_id),
            "body": msg.body[:220], "at": msg.created_at,
            "suggested_owner_id": owner,
            "suggested_owner": display_name_for(owner),
            "matched": matched[:4],
        })
    created: List[Dict[str, Any]] = []
    if create:
        for s in suggestions:
            res = create_action(
                conversation_id, user_id, title=s["body"][:120],
                kind="task", message_id=s["message_id"], owner_id=s["suggested_owner_id"],
                detail="Auto-extracted from message", announce=False,
            )
            if "action" in res:
                created.append(res["action"])
    return {"conversation_id": conversation_id, "suggestions": len(suggestions),
            "items": suggestions, "created": len(created), "created_actions": created,
            "method": "rules-based pattern match (imperatives, requests, assignments, questions)"}


# ============================================================
# NOTIFICATIONS  (queue, preferences, quiet hours, outbox, dispatch)
# ============================================================


def notification_view(notif: NotificationRecord) -> Dict[str, Any]:
    return {
        "id": notif.id, "user_id": notif.user_id, "category": notif.category,
        "title": notif.title, "body": notif.body, "conversation_id": notif.conversation_id,
        "message_id": notif.message_id, "property_id": notif.property_id,
        "actor_id": notif.actor_id, "actor_name": display_name_for(notif.actor_id) if notif.actor_id else None,
        "channels": notif.channels, "delivered": notif.delivered, "status": notif.status,
        "priority": notif.priority, "deep_link": notif.deep_link,
        "created_at": notif.created_at, "read_at": notif.read_at, "attempts": notif.attempts,
    }


def _deep_link(conversation_id: Optional[str] = None, message_id: Optional[str] = None) -> str:
    base = MESSAGING_CONFIG["deep_link_base"]
    parts = [f"c={conversation_id}"] if conversation_id else []
    if message_id:
        parts.append(f"m={message_id}")
    return base + ("?" + "&".join(parts) if parts else "")


def get_preferences(user_id: str) -> Dict[str, Any]:
    profile = ensure_profile(user_id)
    link = _get(telegram_db, "user_id", user_id)
    return {
        "user_id": user_id, "display_name": profile.display_name,
        "notification_prefs": profile.notification_prefs,
        "quiet_hours": profile.quiet_hours, "digest": profile.digest,
        "telegram_opt_in": profile.telegram_opt_in,
        "telegram_linked": bool(link and link.active),
        "categories": list(NOTIFICATION_CATEGORIES),
        "channels": OUTBOX_CHANNELS,
    }


def set_preferences(user_id: str, prefs: Optional[Dict[str, Any]] = None,
                    quiet_hours: Optional[Dict[str, str]] = None, digest: Optional[str] = None,
                    telegram_opt_in: Optional[bool] = None,
                    telegram_categories: Optional[List[str]] = None) -> Dict[str, Any]:
    """Update a user's per-category delivery channels, quiet hours and digest."""
    profile = ensure_profile(user_id)
    if prefs:
        for key, channels in prefs.items():
            if key not in NOTIFICATION_CATEGORIES:
                return {"error": f"unknown category '{key}'",
                        "categories": list(NOTIFICATION_CATEGORIES)}
            bad = [c for c in channels if c not in OUTBOX_CHANNELS]
            if bad:
                return {"error": f"unknown channels {bad}", "channels": OUTBOX_CHANNELS}
            profile.notification_prefs[key] = list(channels)
    if quiet_hours is not None:
        profile.quiet_hours = {"start": quiet_hours.get("start", "21:00"),
                               "end": quiet_hours.get("end", "08:00")}
    if digest in ("instant", "hourly", "daily"):
        profile.digest = digest
    if telegram_opt_in is not None:
        profile.telegram_opt_in = telegram_opt_in
    link = _get(telegram_db, "user_id", user_id)
    if link and telegram_categories is not None:
        link.categories = list(telegram_categories)
    _audit(user_id, "preferences.updated", "user", user_id)
    return get_preferences(user_id)


def _in_quiet_hours(profile: MsgProfile, now: Optional[datetime] = None) -> bool:
    qh = profile.quiet_hours or MESSAGING_CONFIG["quiet_hours"]
    try:
        start = time.fromisoformat(qh.get("start", "21:00"))
        end = time.fromisoformat(qh.get("end", "08:00"))
    except ValueError:
        return False
    moment = (now or _now_dt()).time()
    if start <= end:
        return start <= moment < end
    return moment >= start or moment < end   # crosses midnight


def _resolve_channels(profile: MsgProfile, category: str, urgent: bool,
                      override: Optional[List[str]] = None) -> List[str]:
    base = list(override) if override else list(profile.notification_prefs.get(
        category, NOTIFICATION_CATEGORIES.get(category, {}).get("channels", ["in_app"])))
    if "in_app" not in base:
        base.insert(0, "in_app")
    if "telegram" in base:
        link = _get(telegram_db, "user_id", profile.user_id)
        if not (profile.telegram_opt_in and link and link.active
                and (not link.categories or category in link.categories)):
            base.remove("telegram")
    if MESSAGING_CONFIG["email"]["digest"] != "instant" and not urgent:
        base = [c for c in base if c != "email"]
    return base


def queue_notification(user_id: str, category: str, title: str, body: str = "",
                       actor_id: Optional[str] = None, conversation_id: Optional[str] = None,
                       message_id: Optional[str] = None, property_id: Optional[str] = None,
                       priority: Optional[str] = None, channels: Optional[List[str]] = None) -> Optional[NotificationRecord]:
    """Queue a notification for a user, resolving channels from preferences."""
    if not user_id:
        return None
    profile = ensure_profile(user_id)
    if profile is None:
        return None
    cfg = NOTIFICATION_CATEGORIES.get(category, {})
    urgent = bool(cfg.get("urgent")) or priority == "high"
    resolved = _resolve_channels(profile, category, urgent, override=channels)
    notif = NotificationRecord(
        user_id=user_id, category=category, title=title, body=body, actor_id=actor_id,
        conversation_id=conversation_id, message_id=message_id, property_id=property_id,
        channels=resolved, priority=priority or ("high" if urgent else "normal"),
        deep_link=_deep_link(conversation_id, message_id),
    )
    notifications_db.append(notif)
    return notif


def _notify_new_message(conv: Conversation, msg: Message) -> None:
    if conv.kind == "direct":
        category = "direct"
    elif conv.kind == "property":
        category = "property"
    else:
        category = "channel"
    preview = msg.body[:140] + ("…" if len(msg.body) > 140 else "")
    for member in members_of(conv.id):
        if member.user_id == msg.author_id:
            continue
        mentioned = member.user_id in msg.mentions
        if member.notification_level == "none" and not mentioned:
            continue
        if member.notification_level == "mentions" and not mentioned:
            continue
        if member.muted and not mentioned:
            continue
        cat = "mention" if mentioned else category
        title = (f"{display_name_for(msg.author_id)} mentioned you in {conv.title}"
                 if mentioned else
                 (f"New message from {display_name_for(msg.author_id)}" if conv.kind == "direct"
                  else f"{display_name_for(msg.author_id)} in {conv.title}"))
        queue_notification(
            member.user_id, cat, title=title, body=preview, actor_id=msg.author_id,
            conversation_id=conv.id, message_id=msg.id, property_id=conv.property_id,
        )


def _render_email(notif: NotificationRecord, profile: MsgProfile) -> Dict[str, Any]:
    subject = f"{MESSAGING_CONFIG['email']['subject_prefix']} {notif.title}"
    lines = [f"Hello {profile.display_name or 'there'},", "", notif.body or notif.title]
    if notif.deep_link:
        lines += ["", f"Open in {MESSAGING_CONFIG['workspace']}: {notif.deep_link}"]
    lines += ["", "— Watan-e-Pak Portal (automated notification)"]
    return {"to": profile.email, "subject": subject, "body": "\n".join(lines),
            "from": MESSAGING_CONFIG["email"]["from"],
            "reply_to": MESSAGING_CONFIG["email"]["reply_to"],
            "attachments": []}   # e-mail never carries chat attachments


def _telegram_safe(text: str, has_attachment: bool = False) -> str:
    """Keep Telegram payloads short and free of confidential material."""
    limit = MESSAGING_CONFIG["telegram"]["max_text"]
    text = (text or "").strip()
    if has_attachment:
        text = text.split("\n")[0]
    return text[:limit] + ("…" if len(text) > limit else "")


def _render_telegram(notif: NotificationRecord, profile: MsgProfile) -> Dict[str, Any]:
    text = _telegram_safe(f"{notif.title}\n{notif.body}\n{notif.deep_link}")
    return {"chat_id": (_get(telegram_db, "user_id", notif.user_id) or TelegramLink(
                user_id=notif.user_id, chat_id="")).chat_id,
            "text": text, "parse_mode": "HTML", "disable_web_page_preview": True,
            "attachments": []}


def dispatch_pending(user_id: Optional[str] = None, limit: int = 200,
                     force: bool = False, include_deferred: bool = True) -> Dict[str, Any]:
    """Drain the notification queue into the outbox (the background-worker seam)."""
    pending_states = ["queued"] + (["deferred"] if include_deferred else [])
    rows = [n for n in notifications_db
            if n.status in pending_states and (user_id is None or n.user_id == user_id)]
    rows.sort(key=lambda n: n.created_at)
    sent = deferred = failed = 0
    items: List[Dict[str, Any]] = []
    for notif in rows[:limit]:
        profile = find_profile(notif.user_id)
        if profile is None:
            notif.status = "failed"
            failed += 1
            continue
        notif.attempts += 1
        if not force and notif.priority != "high" and _in_quiet_hours(profile):
            notif.status = "deferred"
            deferred += 1
            continue
        delivered: List[str] = []
        for channel in notif.channels:
            if channel == "in_app":
                out = OutboxItem(channel="in_app", notification_id=notif.id, user_id=notif.user_id,
                                 subject=notif.title, body=notif.body, provider="in_process",
                                 payload={"deep_link": notif.deep_link})
            elif channel == "email":
                payload = _render_email(notif, profile)
                out = OutboxItem(channel="email", notification_id=notif.id, user_id=notif.user_id,
                                 recipient=payload.get("to"), subject=payload["subject"],
                                 body=payload["body"], payload=payload)
            elif channel == "telegram":
                payload = _render_telegram(notif, profile)
                out = OutboxItem(channel="telegram", notification_id=notif.id, user_id=notif.user_id,
                                 recipient=payload.get("chat_id"), subject=notif.title,
                                 body=payload["text"], payload=payload)
            else:  # pragma: no cover - guarded at queue time
                continue
            outbox_db.append(out)
            delivered.append(channel)
            items.append({"notification_id": notif.id, "channel": channel,
                          "recipient": out.recipient, "status": out.status})
        notif.delivered = delivered
        notif.status = "sent" if delivered else "failed"
        if delivered:
            sent += 1
        else:
            failed += 1
    return {"dispatched": sent, "deferred": deferred, "failed": failed,
            "scanned": len(rows), "items": items}


def notifications(user_id: str, unread_only: bool = False, category: Optional[str] = None,
                  limit: int = 50) -> Dict[str, Any]:
    rows = [n for n in notifications_db if n.user_id == user_id
            and (category is None or n.category == category)
            and (not unread_only or n.status != "read")]
    rows.sort(key=lambda n: n.created_at, reverse=True)
    total = len(rows)
    if limit and limit > 0:
        rows = rows[:limit]
    return {"user_id": user_id, "count": total,
            "unread": len([n for n in notifications_db if n.user_id == user_id and n.status != "read"]),
            "notifications": [notification_view(n) for n in rows]}


def read_notification(notification_id: str, user_id: str) -> Dict[str, Any]:
    notif = _get(notifications_db, "id", notification_id)
    if notif is None:
        return {"error": f"notification '{notification_id}' not found"}
    if notif.user_id != user_id:
        return {"error": "access denied"}
    if notif.status != "read":
        notif.status = "read"
        notif.read_at = _now()
    return {"notification": notification_view(notif)}


def mark_all_notifications_read(user_id: str) -> Dict[str, Any]:
    changed = 0
    for notif in notifications_db:
        if notif.user_id == user_id and notif.status != "read":
            notif.status = "read"
            notif.read_at = _now()
            changed += 1
    return {"user_id": user_id, "marked_read": changed}


def outbox(channel: Optional[str] = None, user_id: Optional[str] = None, limit: int = 100) -> Dict[str, Any]:
    rows = [o for o in outbox_db
            if (channel is None or o.channel == channel)
            and (user_id is None or o.user_id == user_id)]
    rows.sort(key=lambda o: o.created_at, reverse=True)
    by_channel: Dict[str, int] = {}
    for o in outbox_db:
        by_channel[o.channel] = by_channel.get(o.channel, 0) + 1
    return {"count": len(rows), "by_channel": by_channel,
            "items": [o.model_dump() for o in rows[:limit] if limit]}


def unread_summary(user_id: str) -> Dict[str, Any]:
    """Combined unread picture: conversations, mentions, notifications, actions."""
    counts = unread_counts(user_id)
    open_actions = list_actions(user_id, owner_id=user_id, status="open")
    return {
        "user_id": user_id, "display_name": display_name_for(user_id),
        "conversations_unread": counts["total"], "mentions": counts["mentions"],
        "notifications_unread": counts["notifications"],
        "open_actions": open_actions["count"],
        "overdue_actions": open_actions["overdue"],
        "per_conversation": counts["conversations"],
        "via_channel": {"in_app": counts["notifications"]},
    }


# ============================================================
# TELEGRAM  (optional notification channel — opt-in, sanitised payloads)
# ============================================================


def telegram_link_code(user_id: str) -> Dict[str, Any]:
    """Mint a short, single-use code a user pastes to the bot as ``/start CODE``."""
    ensure_profile(user_id)
    code = secrets.token_hex(3).upper()
    expires = _now_dt() + timedelta(minutes=MESSAGING_CONFIG["telegram"]["link_code_ttl_minutes"])
    link_codes_db[code] = {"user_id": user_id, "expires_at": expires.isoformat(timespec="seconds")}
    return {
        "user_id": user_id, "code": code,
        "expires_at": expires.isoformat(timespec="seconds"),
        "instructions": f"Send /start {code} to @{MESSAGING_CONFIG['telegram']['bot_name']}",
        "bot": MESSAGING_CONFIG["telegram"]["bot_name"],
    }


def telegram_link(user_id: str, chat_id: str, username: Optional[str] = None,
                  categories: Optional[List[str]] = None) -> Dict[str, Any]:
    """Opt a user in: bind a Telegram chat id and the categories they will receive."""
    ensure_profile(user_id)
    cats = [c for c in (categories or list(NOTIFICATION_CATEGORIES)) if c in NOTIFICATION_CATEGORIES]
    existing = _get(telegram_db, "user_id", user_id)
    if existing:
        existing.chat_id = chat_id
        existing.username = username or existing.username
        existing.active = True
        existing.categories = cats
        link = existing
    else:
        link = TelegramLink(user_id=user_id, chat_id=chat_id, username=username, categories=cats)
        telegram_db.append(link)
    profile = find_profile(user_id)
    if profile:
        profile.telegram_opt_in = True
    _audit(user_id, "telegram.linked", "user", user_id, detail=f"chat {chat_id}")
    return {"link": link.model_dump(), "categories": cats}


def telegram_unlink(user_id: str) -> Dict[str, Any]:
    link = _get(telegram_db, "user_id", user_id)
    if link:
        link.active = False
    profile = find_profile(user_id)
    if profile:
        profile.telegram_opt_in = False
    _audit(user_id, "telegram.unlinked", "user", user_id)
    return {"user_id": user_id, "unlinked": True}


def telegram_links(active_only: bool = True) -> Dict[str, Any]:
    rows = [t for t in telegram_db if not active_only or t.active]
    return {"count": len(rows), "links": [t.model_dump() for t in rows]}


def telegram_status(user_id: str) -> Dict[str, Any]:
    profile = ensure_profile(user_id)
    link = _get(telegram_db, "user_id", user_id)
    return {"user_id": user_id, "opt_in": profile.telegram_opt_in,
            "linked": bool(link and link.active),
            "chat_id": link.chat_id if link else None,
            "categories": link.categories if link else [],
            "bot": MESSAGING_CONFIG["telegram"]["bot_name"],
            "policy": "Short text and an authenticated deep link only — no documents."}


def telegram_handle_update(update: Dict[str, Any]) -> Dict[str, Any]:
    """Process one inbound Telegram bot update (commands) without calling Telegram."""
    message = (update or {}).get("message") or (update or {}).get("edited_message") or {}
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id", ""))
    username = chat.get("username")
    text = (message.get("text") or "").strip()
    parts = text.split()
    command = parts[0].lower() if parts else ""
    arg = parts[1] if len(parts) > 1 else None
    reply = ""
    action = "noop"
    linked_user = None
    link = _get(telegram_db, "chat_id", chat_id) if chat_id else None

    if command in ("/start", "/link"):
        if arg:
            entry = link_codes_db.get(arg.upper())
            if entry and _parse_iso(entry["expires_at"]) and _now_dt() <= _parse_iso(entry["expires_at"]):
                linked_user = entry["user_id"]
                telegram_link(linked_user, chat_id, username)
                link_codes_db.pop(arg.upper(), None)
                reply = f"Linked to {MESSAGING_CONFIG['workspace']}. You will get optional alerts here."
                action = "linked"
            else:
                reply = "That link code is invalid or expired. Generate a new one in the portal."
                action = "link_failed"
        else:
            reply = (f"Welcome to {MESSAGING_CONFIG['workspace']} alerts. "
                     f"Send /start <code> to link your account.")
            action = "greeting"
    else:
        link = next((t for t in telegram_db if t.chat_id == chat_id and t.active), None)
        linked_user = link.user_id if link else None
        if link is None:
            reply = "This chat is not linked. Send /start <code> from the portal to link it."
            action = "unlinked"
        elif command in ("/stop", "/unlink"):
            telegram_unlink(link.user_id)
            reply = "Unlinked. You will no longer receive Telegram alerts."
            action = "unlinked"
        elif command == "/mute":
            link.categories = []
            reply = "Muted. Send /unmute to resume all categories."
            action = "muted"
        elif command == "/unmute":
            link.categories = list(NOTIFICATION_CATEGORIES)
            reply = "All notification categories enabled."
            action = "unmuted"
        elif command == "/digest":
            summary = unread_summary(link.user_id)
            reply = (f"{summary['conversations_unread']} unread messages, "
                     f"{summary['mentions']} mentions, {summary['open_actions']} open tasks.")
            action = "digest"
        elif command == "/status":
            profile = find_profile(link.user_id)
            reply = (f"Presence: {profile.presence if profile else 'offline'}. "
                     f"Categories: {', '.join(link.categories) or 'none'}.")
            action = "status"
        else:
            reply = f"Commands: /digest /status /mute /unmute /stop — or open {MESSAGING_CONFIG['deep_link_base']}."
            action = "help"

    if link and linked_user == link.user_id:
        link.last_update_at = _now()
    _audit(linked_user, f"telegram.update.{action}", "telegram", chat_id, detail=command)
    return {"ok": True, "action": action, "user_id": linked_user, "chat_id": chat_id,
            "reply": _telegram_safe(reply), "reply_html": _telegram_safe(reply)}


def telegram_alert(user_id: str, text: str, priority: str = "normal",
                   conversation_id: Optional[str] = None,
                   message_id: Optional[str] = None) -> Dict[str, Any]:
    """Queue and immediately dispatch a Telegram-only alert (sanitised, with deep link)."""
    notif = queue_notification(
        user_id, "system", title="Watan-e-Pak alert", body=_telegram_safe(text),
        conversation_id=conversation_id, message_id=message_id, priority=priority,
        channels=["telegram"],
    )
    if notif is None:
        return {"error": f"user '{user_id}' has no messaging profile"}
    result = dispatch_pending(user_id=user_id, limit=5, force=priority == "high")
    item = next((o for o in outbox_db if o.notification_id == notif.id and o.channel == "telegram"), None)
    return {"queued": notification_view(notif), "dispatched": result["dispatched"],
            "deferred": result["deferred"], "telegram_item": item.model_dump() if item else None}


# ============================================================
# AUDIT
# ============================================================


def list_audit(limit: int = 100, action: Optional[str] = None, actor_id: Optional[str] = None,
               target_type: Optional[str] = None) -> Dict[str, Any]:
    rows = [e for e in audit_db
            if (action is None or e.action == action)
            and (actor_id is None or e.actor_id == actor_id)
            and (target_type is None or e.target_type == target_type)]
    rows.sort(key=lambda e: e.at, reverse=True)
    actions: Dict[str, int] = {}
    for e in audit_db:
        actions[e.action] = actions.get(e.action, 0) + 1
    return {"count": len(rows), "actions": actions,
            "events": [e.model_dump() for e in rows[:limit] if limit]}


# ============================================================
# RETENTION & DELETION POLICY
# ============================================================


def retention_report() -> Dict[str, Any]:
    """Per-conversation retention picture: what is eligible for purge and why."""
    rows: List[Dict[str, Any]] = []
    today = date.today()
    for conv in conversations_db:
        live = [m for m in messages_db if m.conversation_id == conv.id and not m.deleted_at]
        cutoff = today - timedelta(days=conv.retention_days)
        eligible = [m for m in live if not m.pinned
                    and (_parse_iso(m.created_at) or _now_dt()).date() < cutoff]
        rows.append({
            "conversation_id": conv.id, "title": conv.title, "kind": conv.kind,
            "retention_days": conv.retention_days, "cutoff": cutoff.isoformat(),
            "messages": len(live), "pinned": len([m for m in live if m.pinned]),
            "purgeable": len(eligible),
            "oldest": min((m.created_at for m in live), default=None),
        })
    return {
        "default_retention_days": MESSAGING_CONFIG["retention_days_default"],
        "policy": "Soft-delete then purge; pinned messages are exempt; every purge is audited.",
        "conversations": rows,
        "purgeable_total": sum(r["purgeable"] for r in rows),
    }


def purge_retention(dry_run: bool = True, retention_days: Optional[int] = None,
                    actor_id: Optional[str] = None) -> Dict[str, Any]:
    """Apply the retention policy: soft-delete messages past the window (pinned exempt)."""
    today = date.today()
    purged: List[Dict[str, Any]] = []
    for conv in conversations_db:
        days = retention_days or conv.retention_days
        cutoff = today - timedelta(days=days)
        for msg in messages_db:
            if msg.conversation_id != conv.id or msg.deleted_at or msg.pinned:
                continue
            created = (_parse_iso(msg.created_at) or _now_dt()).date()
            if created < cutoff:
                purged.append({"conversation_id": conv.id, "message_id": msg.id,
                               "seq": msg.seq, "created_at": msg.created_at})
                if not dry_run:
                    msg.deleted_at = _now()
                    msg.deleted_by = actor_id or "system"
                    msg.deleted_reason = "retention"
    if not dry_run and purged:
        _audit(actor_id or "system", "retention.purged", "message", None,
               detail=f"{len(purged)} messages purged", meta={"count": len(purged)})
    return {"dry_run": dry_run, "purgeable": len(purged),
            "purged": 0 if dry_run else len(purged), "messages": purged[:200]}


# ============================================================
# MODERATION & SPAM CONTROLS
# ============================================================


def report_message(message_id: str, reporter_id: str, reason: str = "other",
                   detail: Optional[str] = None) -> Dict[str, Any]:
    msg = _get(messages_db, "id", message_id)
    if msg is None:
        return {"error": f"message '{message_id}' not found"}
    if reason not in REPORT_REASONS:
        return {"error": f"reason must be one of {REPORT_REASONS}"}
    conv = _get(conversations_db, "id", msg.conversation_id)
    if conv and not can_access(conv, reporter_id):
        return {"error": "access denied"}
    report = MessageReport(message_id=message_id, conversation_id=msg.conversation_id,
                           reporter_id=reporter_id, reason=reason, detail=detail)
    reports_db.append(report)
    _audit(reporter_id, "message.reported", "message", message_id, detail=reason)
    return {"report": report.model_dump()}


def list_reports(status: Optional[str] = None, limit: int = 100) -> Dict[str, Any]:
    rows = [r for r in reports_db if status is None or r.status == status]
    rows.sort(key=lambda r: r.created_at, reverse=True)
    by_status: Dict[str, int] = {}
    for r in reports_db:
        by_status[r.status] = by_status.get(r.status, 0) + 1
    return {"count": len(rows), "by_status": by_status,
            "reports": [r.model_dump() for r in rows[:limit] if limit]}


def moderate_report(report_id: str, actor_id: str, action: str,
                    note: Optional[str] = None) -> Dict[str, Any]:
    """Resolve a report: dismiss, delete the message, mute the author or escalate."""
    report = _get(reports_db, "id", report_id)
    if report is None:
        return {"error": f"report '{report_id}' not found"}
    if action not in MODERATION_ACTIONS:
        return {"error": f"action must be one of {MODERATION_ACTIONS}"}
    msg = _get(messages_db, "id", report.message_id)
    outcome = action
    if action == "delete_message" and msg:
        delete_message(msg.id, actor_id, reason="moderation")
    elif action == "mute_author" and msg and msg.author_id:
        muted_authors_db[msg.author_id] = {"by": actor_id, "at": _now(), "reason": note or report.reason}
    elif action == "escalate":
        report.status = "resolved"
    elif action == "dismiss":
        report.status = "dismissed"
    if action in ("delete_message", "mute_author"):
        report.status = "resolved"
    report.resolution = action + (f": {note}" if note else "")
    report.resolved_by = actor_id
    report.resolved_at = _now()
    _audit(actor_id, f"report.{action}", "report", report.id, detail=note)
    return {"report": report.model_dump(), "outcome": outcome,
            "muted_authors": list(muted_authors_db)}


# ============================================================
# DIGEST & WING STATISTICS
# ============================================================


def conversation_digest(conversation_id: str, user_id: str, days: int = 7) -> Dict[str, Any]:
    """Recent-activity digest for a conversation over a window."""
    conv = _get(conversations_db, "id", conversation_id)
    if conv is None:
        return {"error": f"conversation '{conversation_id}' not found"}
    if not can_access(conv, user_id):
        return {"error": "access denied"}
    since = _now_dt() - timedelta(days=days)
    rows = [m for m in messages_db
            if m.conversation_id == conversation_id and not m.deleted_at
            and (_parse_iso(m.created_at) or _now_dt()) >= since]
    rows.sort(key=lambda m: m.seq)
    authors: Dict[str, int] = {}
    for m in rows:
        authors[m.author_id or "system"] = authors.get(m.author_id or "system", 0) + 1
    return {
        "conversation_id": conversation_id, "title": conv.title, "days": days,
        "messages": len(rows), "participants": [{"user_id": k, "name": display_name_for(k), "messages": v}
                                                for k, v in sorted(authors.items(), key=lambda kv: -kv[1])],
        "attachments": len([a for a in attachments_db if a.conversation_id == conversation_id]),
        "open_actions": len([a for a in actions_db if a.conversation_id == conversation_id
                             and a.status in ("open", "in_progress")]),
        "highlights": [message_view(m) for m in rows[-5:]],
    }


def messaging_statistics() -> Dict[str, Any]:
    """Aggregate wing statistics for the portal dashboard."""
    kinds: Dict[str, int] = {}
    for conv in conversations_db:
        kinds[conv.kind] = kinds.get(conv.kind, 0) + 1
    channels: Dict[str, int] = {}
    for conv in conversations_db:
        if conv.channel_key:
            channels[conv.channel_key] = channels.get(conv.channel_key, 0) + 1
    by_category: Dict[str, int] = {}
    by_channel: Dict[str, int] = {}
    for n in notifications_db:
        by_category[n.category] = by_category.get(n.category, 0) + 1
    for o in outbox_db:
        by_channel[o.channel] = by_channel.get(o.channel, 0) + 1
    return {
        "workspace": MESSAGING_CONFIG["workspace"],
        "profiles": len(profiles_db),
        "online": len([p for p in profiles_db if p.presence == "online"]),
        "conversations": len(conversations_db), "by_kind": kinds, "by_channel": channels,
        "messages": len(messages_db),
        "messages_live": len([m for m in messages_db if not m.deleted_at]),
        "attachments": len(attachments_db),
        "attachments_confidential": len([a for a in attachments_db if a.sensitivity != "normal"]),
        "actions": len(actions_db),
        "actions_open": len([a for a in actions_db if a.status in ("open", "in_progress")]),
        "notifications": len(notifications_db), "by_category": by_category,
        "outbox": len(outbox_db), "outbox_by_channel": by_channel,
        "telegram_opt_in": len([t for t in telegram_db if t.active]),
        "audit_events": len(audit_db),
        "open_reports": len([r for r in reports_db if r.status == "open"]),
        "store": "in-memory (behind the _store seam; migrate to PostgreSQL messaging schema)",
    }


# ============================================================
# SEED  (demo team, channels and a property discussion)
# ============================================================


def seed_demo(users: List[Dict[str, Any]], property_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    """Seed profiles from portal users, open the default channels and a demo thread."""
    property_ids = property_ids or []
    for row in users:
        ensure_profile(
            user_id=row["user_id"], display_name=row.get("display_name") or row.get("name") or "",
            role=row.get("role") or "member", handle=row.get("handle"),
            email=row.get("email"), mobile=row.get("mobile"), title=row.get("title"),
        )
    admin = next((r["user_id"] for r in users if (r.get("role") in ADMIN_ROLES)), None)
    if admin is None and users:
        admin = users[0]["user_id"]
    member_one = next((r["user_id"] for r in users if r["user_id"] != admin), None)
    created: List[str] = []

    for channel in DEFAULT_CHANNELS:
        if any(c.channel_key == channel["key"] for c in conversations_db):
            continue
        participants = [admin] if channel["restricted"] and admin else [r["user_id"] for r in users[:6]]
        result = create_conversation(
            kind="channel", channel_key=channel["key"], created_by=admin or (users[0]["user_id"] if users else None),
            participants=participants, announcement=f"Welcome to #{channel['name']} — {channel['purpose']}.",
        )
        if "conversation" in result:
            created.append(result["conversation"]["id"])

    if admin and member_one:
        dm = get_or_create_direct(admin, member_one)
        if "conversation" in dm:
            conv_id = dm["conversation"]["id"]
            post_message(conv_id, admin, "Welcome aboard — this is our internal messaging workspace.")
            post_message(conv_id, member_one, "Great. I'll keep property discussions in the linked threads.")

    if property_ids and admin:
        thread = get_or_create_property_thread(property_ids[0], created_by=admin,
                                               title=f"Property {property_ids[0]}")
        if "conversation" in thread:
            conv_id = thread["conversation"]["id"]
            post_message(conv_id, admin, "Opened the discussion for this listing. Please verify the title documents.")
            register_attachment(conv_id, admin, "title-deed.pdf", kind="pdf", size_bytes=512000,
                                sensitivity="confidential", linked_type="property", linked_id=property_ids[0])
            post_message(conv_id, member_one, "Noted — I will check the registry record and map the boundary.")

    sales = next((c for c in conversations_db if c.channel_key == "sales"), None)
    if sales and admin:
        post_message(sales.id, admin, "Reminder: three new enquiries need attention today.")
        post_message(sales.id, member_one, "@" + (find_profile(admin).handle if find_profile(admin) else "admin")
                     + " please share the latest rate list for DHA Phase 6.")

    dispatch_pending(force=True)
    return {"channels": len(created), "conversations": len(conversations_db),
            "profiles": len(profiles_db), "messages": len(messages_db)}

