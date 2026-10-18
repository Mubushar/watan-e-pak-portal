"""
Access control for the CRM family of routes — /crm, /marketing, /broker, /agents, /messaging.

One ASGI middleware decides, from the method and path, what a request needs:

* **public**      the portal's own visitor features: an enquiry or viewing request from a
                  property page (``POST /crm/leads``, ``POST /crm/appointments``, rate-limited per
                  IP), the agent contact card (``GET /crm/agents``, trimmed to public fields), the
                  listing marketing kit, the AI Hub's agent catalogue, and inbound webhooks.
* **signed in**   running Agentic-OS agents; team messaging (and the ids a request acts as —
                  ``author_id``, ``actor_id``, ``created_by``, ``uploaded_by``, ``user_id`` in the
                  body, query or path — must be the signed-in user's, unless an admin).
* **crm.view**    reading the CRM, marketing and broker data.
* **crm.manage**  changing it.

The signed-in user is kept in a context variable for the routes: ``current()``, and
``agent_scope()`` — the CRM agent id a plain agent is limited to (they see only their own book).
"""

from __future__ import annotations

import json
import re
import time
from collections import defaultdict, deque
from contextvars import ContextVar
from typing import Any, Callable, Deque, Dict, Optional, Tuple
from urllib.parse import parse_qs

_user: ContextVar[Optional[Dict[str, Any]]] = ContextVar("portal_user", default=None)

ADMIN_ROLES = {"super_admin", "admin"}
# Roles that see the whole CRM; a user whose only CRM role is "agent" sees their own book.
TEAM_ROLES = ADMIN_ROLES | {"agency_manager", "customer_support", "moderator", "auditor"}
IDENTITY_KEYS = ("author_id", "actor_id", "created_by", "uploaded_by", "user_id")
# Messaging routes where ``user_id`` names someone else (the person being removed / alerted).
USER_ID_IS_TARGET = re.compile(r"^/messaging/(revoke-access|telegram/alert|dispatch)$")
PUBLIC_RATE = (20, 60.0)  # public enquiries: 20 per IP per minute

_hits: Dict[str, Deque[float]] = defaultdict(deque)


def current() -> Optional[Dict[str, Any]]:
    return _user.get()


def is_admin(user: Optional[Dict[str, Any]]) -> bool:
    if not user:
        return False
    roles = set(user.get("roles") or [user.get("role")])
    return bool(roles & ADMIN_ROLES) or "users.manage" in (user.get("permissions") or [])


def can(user: Optional[Dict[str, Any]], permission: str) -> bool:
    if not user:
        return False
    roles = set(user.get("roles") or [user.get("role")])
    return "super_admin" in roles or permission in (user.get("permissions") or [])


def agent_scope(user: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """The CRM agent id a plain agent is limited to; None for team / admin users (or no user).
    An agent account not yet linked to a CRM agent gets a scope that matches nothing."""
    user = user if user is not None else current()
    if not user:
        return None
    roles = set(user.get("roles") or [user.get("role")])
    if roles & TEAM_ROLES or "agent" not in roles:
        return None
    return user.get("agent_id") or "__unlinked__"


# ------------------------------------------------------------------ rules

Rule = str  # "public" | "user" | "crm.view" | "crm.manage" | "none"

_PUBLIC_AGENT_READS = re.compile(r"^/agents/(catalog|products|overview|portal|[a-z0-9_-]+)$")
_CRM_AGENT_TOOLS = re.compile(r"^/agents/(smart-actions|move-likelihood(/.*)?|seller-intent)$")
_AGENT_RUNS = re.compile(r"^/agents/(run|plan|orchestrate|runs(/.*)?)$")


def rule_for(method: str, path: str) -> Rule:
    if path.startswith("/crm/webhooks/"):
        return "public"
    if path in ("/crm/leads", "/crm/appointments") and method == "POST":
        return "public"
    if path == "/crm/agents" and method == "GET":
        return "public"
    if path.startswith("/broker/listing-draft/") and method == "GET":
        return "public"
    if path == "/messaging/telegram/update":
        return "public"
    if path.startswith("/agents/"):
        if _CRM_AGENT_TOOLS.match(path):
            return "crm.view" if method == "GET" else "crm.manage"
        if _AGENT_RUNS.match(path):
            return "user"
        if method == "GET" and _PUBLIC_AGENT_READS.match(path):
            return "public"
        return "user"
    if path.startswith("/admin/basedata"):
        return "basedata.manage"
    if path.split("/")[1:2] in (["cities"], ["schemes"], ["blocks"]) and method in ("POST", "PUT", "PATCH", "DELETE"):
        return "basedata.manage"
    if path.startswith(("/crm/", "/marketing/", "/broker/")) or path in ("/crm", "/marketing", "/broker"):
        return "crm.view" if method in ("GET", "HEAD") else "crm.manage"
    if path.startswith("/messaging/") or path == "/messaging":
        return "user"
    return "none"


def _limited(ip: str) -> bool:
    n, window = PUBLIC_RATE
    now = time.monotonic()
    q = _hits[ip]
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= n:
        return True
    q.append(now)
    return False


def _identity_mismatch(user: Dict[str, Any], path: str, query: Dict[str, list], body: Any) -> Optional[str]:
    """For messaging: the ids a request acts as must be the signed-in user's."""
    if is_admin(user):
        return None
    me = user.get("id")
    keys = [k for k in IDENTITY_KEYS if not (k == "user_id" and USER_ID_IS_TARGET.match(path))]
    for k in keys:
        for v in query.get(k, []):
            if v and v != me:
                return k
        if isinstance(body, dict) and body.get(k) and body.get(k) != me:
            return k
    m = re.match(r"^/messaging/(preferences|unread|notifications|unread-summary|telegram/status)/([^/]+)", path)
    if m and m.group(2) != me:
        return "user"
    return None


class AccessGuard:
    """ASGI middleware enforcing ``rule_for``; also publishes the user to ``current()``."""

    def __init__(self, app: Callable, resolve_user: Callable[[Optional[str]], Optional[Dict[str, Any]]],
                 owner_of: Optional[Callable[[str, str], Tuple[bool, Optional[str]]]] = None) -> None:
        self.app = app
        self.resolve_user = resolve_user
        self.owner_of = owner_of

    async def __call__(self, scope: Dict[str, Any], receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        method = scope["method"]
        path = scope["path"]
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        auth = headers.get("authorization", "")
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else (auth.strip() or None)
        user = self.resolve_user(token) if token else None
        reset = _user.set(user)
        try:
            rule = rule_for(method, path)
            if method == "OPTIONS" or rule in ("none",):
                await self.app(scope, receive, send)
                return
            if rule == "public":
                if method == "POST" and path in ("/crm/leads", "/crm/appointments") and not user:
                    ip = (headers.get("x-forwarded-for", "").split(",")[0].strip() or (scope.get("client") or ("?",))[0])
                    if _limited(ip):
                        await _deny(send, 429, "Too many requests — please try again in a minute")
                        return
                await self.app(scope, receive, send)
                return
            if not user:
                await _deny(send, 401, "Please sign in to use this feature", {"WWW-Authenticate": "Bearer"})
                return
            if rule.endswith((".view", ".manage")) and not can(user, rule):
                await _deny(send, 403, f"Your role doesn't include {rule.replace('.', ' ')} access")
                return
            mine = agent_scope(user)
            if path.startswith("/messaging") or (mine and self.owner_of and path.startswith(("/crm", "/agents/move-likelihood"))):
                body_bytes, receive = await _buffer(receive)
                try:
                    body = json.loads(body_bytes) if body_bytes else None
                except ValueError:
                    body = None
                if path.startswith("/messaging"):
                    bad = _identity_mismatch(user, path, parse_qs(scope.get("query_string", b"").decode()), body)
                    if bad:
                        await _deny(send, 403, f"You can only act as yourself ({bad} doesn't match your account)")
                        return
                elif mine and self.owner_of:
                    for kind, ident in _targets(path, body):
                        found, owner = self.owner_of(kind, ident)
                        if found and owner != mine:
                            await _deny(send, 403, f"This {kind} belongs to another agent")
                            return
            await self.app(scope, receive, send)
        finally:
            _user.reset(reset)


_TARGET_PATHS = [
    (re.compile(r"^/crm/leads/([^/]+)"), "lead"),
    (re.compile(r"^/crm/ai/lead-brief/([^/]+)"), "lead"),
    (re.compile(r"^/agents/move-likelihood/([^/]+)"), "lead"),
    (re.compile(r"^/crm/customers/([^/]+)"), "customer"),
    (re.compile(r"^/crm/deals/([^/]+)/"), "deal"),
    (re.compile(r"^/crm/tasks/([^/]+)/"), "task"),
]


def _targets(path: str, body: Any) -> list:
    """The CRM records a request reads or changes (for the agent-owns-it check)."""
    out = []
    for rx, kind in _TARGET_PATHS:
        m = rx.match(path)
        if m:
            out.append((kind, m.group(1)))
    if isinstance(body, dict):
        if body.get("entity_id") and body.get("entity_type", "lead") in ("lead", "customer"):
            out.append((body.get("entity_type") or "lead", str(body["entity_id"])))
        for key, kind in (("lead_id", "lead"), ("customer_id", "customer")):
            if body.get(key):
                out.append((kind, str(body[key])))
    return out


async def _buffer(receive: Callable) -> Tuple[bytes, Callable]:
    """Read the whole request body and return a receive() that replays it."""
    chunks = []
    more = True
    while more:
        msg = await receive()
        chunks.append(msg.get("body", b""))
        more = msg.get("more_body", False)
    body = b"".join(chunks)
    sent = False

    async def replay() -> Dict[str, Any]:
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return await receive()

    return body, replay


async def _deny(send: Callable, status: int, detail: str, extra: Optional[Dict[str, str]] = None) -> None:
    payload = json.dumps({"detail": detail}).encode()
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(payload)).encode())]
    headers += [(k.lower().encode(), v.encode()) for k, v in (extra or {}).items()]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": payload})
