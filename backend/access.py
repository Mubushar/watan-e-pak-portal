"""
Access control for every HTTP route (and the MCP endpoint).

One ASGI middleware decides, from the method and path, what a request needs — see the rule table
below (``_RULES``). Reads are public unless a rule says otherwise; any write that no rule names
needs an administrator (deny by default). Highlights:

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

import hmac
import json
import re
import time
from collections import defaultdict, deque
from contextvars import ContextVar
from typing import Any, Callable, Deque, Dict, Optional, Tuple
from urllib.parse import parse_qs

import portal_env

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

Rule = str
# Rules:  "public"   anyone
#         "user"     any signed-in user
#         "<perm>"   a permission from auth.PERMISSIONS (e.g. "crm.view"; super_admin has all)
#         "admin"    super_admin / admin only
#         "mcp"      the MCP endpoint (PORTAL_MCP_TOKEN, a super_admin token, or a local client)
#         "docs"     API docs (public in development; hidden in production unless enabled)
#         "none"     not covered here (only GET routes fall through to it — they are public)
# Any write (POST / PUT / PATCH / DELETE) that no rule names needs an admin: deny by default.

_R = Tuple[str, "re.Pattern[str]", Rule]
W = "W"  # any write method
_RULES: list = []


def _add(methods: str, pattern: str, rule: Rule) -> None:
    _RULES.append((methods, re.compile(pattern), rule))


# ---- protocol endpoints
_add("*", r"^/mcp(/|$)", "mcp")
_add("*", r"^/(docs|redoc|openapi\.json)(/|$)", "docs")

# ---- authentication & accounts
_add("GET", r"^/auth/(otps|notifications)$", "settings.manage")
_add("GET", r"^/auth/events$", "audit.view")
_add("GET", r"^/auth/users$", "users.view")
_add("*", r"^/auth/", "public")
_add("GET", r"^/roles/[^/]+/users$", "users.view")
_add("GET", r"^/roles(/|$)", "public")            # the role / permission catalogue
_add("*", r"^/roles(/|$)", "roles.manage")
_add("GET", r"^/users/", "users.view")
_add("*", r"^/users/", "roles.manage")
_add("*", r"^/me(/|$)", "user")

# ---- portal administration
_add("GET", r"^/portal/audit$", "audit.view")
_add("*", r"^/portal/settings$", "settings.manage")
_add("*", r"^/portal/storage(/flush)?$", "settings.manage")
_add("*", r"^/memory(/|$)", "settings.manage")
_add(W, r"^/masterplans/knowledge/refresh$", "settings.manage")
_add("*", r"^/admin/basedata(/|$)", "basedata.manage")
_add(W, r"^/(cities|schemes|blocks)(/|$)", "basedata.manage")

# ---- CRM family
_add("*", r"^/crm/webhooks/", "public")
_add("POST", r"^/crm/(leads|appointments)$", "public")      # enquiry / viewing request from a listing
_add("GET", r"^/crm/agents$", "public")                     # agent contact card (trimmed for visitors)
_add("GET", r"^/broker/listing-draft/", "public")
_add("GET", r"^/(crm|marketing|broker)(/|$)", "crm.view")
_add(W, r"^/(crm|marketing|broker)(/|$)", "crm.manage")
_add("*", r"^/agents/(smart-actions|move-likelihood(/.*)?|seller-intent)$", "crm.view")
_add("POST", r"^/agents/runs/[^/]+/approve$", "crm.manage")
_add("*", r"^/agents/(run|plan|orchestrate|runs(/.*)?)$", "user")
_add("GET", r"^/agents/(catalog|products|overview|portal|[a-z0-9_-]+)$", "public")
_add("*", r"^/agents(/|$)", "user")
_add("*", r"^/transactions/terms/extract$", "public")      # a document tool
_add("GET", r"^/transactions(/|$)", "crm.view")
_add(W, r"^/transactions(/|$)", "crm.manage")
_add("POST", r"^/leasing/(apply|inquiries)$", "public")
_add("GET", r"^/leasing/(inquiries|renewals|collection|funnel)$", "crm.view")
_add(W, r"^/leasing(/|$)", "listings.manage")

# ---- messaging
_add("POST", r"^/messaging/telegram/update$", "public")    # bot webhook (secret-token checked)
_add("*", r"^/messaging/(audit|outbox|retention|statistics|telegram/links)$", "audit.view")
_add("POST", r"^/messaging/(purge|dispatch|telegram/alert)$", "settings.manage")
_add("POST", r"^/messaging/reports/[^/]+/moderate$", "settings.manage")
_add("*", r"^/messaging(/|$)", "user")

# ---- money
_add("GET", r"^/accounting(/|$)", "accounting.view")
_add(W, r"^/accounting/(payments|rent-invoices)$", "payments.manage")
_add(W, r"^/accounting(/|$)", "accounting.manage")
_add("GET", r"^/commercial/(plans|pricing|products|gtm|portal)(/|\.html|$)", "public")
_add("POST", r"^/commercial/recommend$", "public")
_add("POST", r"^/commercial/subscribe$", "user")
_add("GET", r"^/commercial(/|$)", "finance.view")
_add(W, r"^/commercial(/|$)", "finance.manage")

# ---- delivery
_add("GET", r"^/pmo(/|$)", "projects.view")
_add(W, r"^/pmo(/|$)", "projects.manage")
_add("POST", r"^/maintenance/report$", "user")
_add("GET", r"^/maintenance/(work-orders|plans)(/|$)", "user")
_add(W, r"^/maintenance(/|$)", "listings.manage")
_add("POST", r"^/construction/estimate$", "public")       # calculator
_add(W, r"^/construction(/|$)", "user")                   # saved estimates / reports

# ---- catalogue & content
_add(W, r"^/properties(/|$)", "properties.manage")
_add(W, r"^/images(/|$)", "listings.manage")
_add(W, r"^/bigprojects(/|$)", "projects.manage")
_add("POST", r"^/content/contacts$", "public")            # the site's contact form
_add(W, r"^/content(/|$)", "content.manage")
_add(W, r"^/news(/|$)", "news.manage")
_add("POST", r"^/ads/[^/]+/(event|track)$", "public")
_add("GET", r"^/ads/(active|config|section)(/|$)", "public")
_add("GET", r"^/ads(/|$)", "ads.view")
_add(W, r"^/ads(/|$)", "ads.manage")

# ---- GIS
_add("POST", r"^/gis/(buffer|buffers|polygon-analysis|properties-in-polygon|route/matrix)$", "public")
_add(W, r"^/gis(/|$)", "gis.manage")
_add("POST", r"^/poi/within-polygon$", "public")
_add(W, r"^/poi(/|$)", "poi.manage")
_add("POST", r"^/aoi/compare$", "public")
_add(W, r"^/aoi(/|$)", "aoi.manage")
_add("POST", r"^/geo/study-area$", "public")

# ---- compute-only tools, calculators, AI (rate-limited by ai_guard)
_add("*", r"^/tools/projects(/|$)", "user")
_add("POST", r"^/tools/", "public")
_add("POST", r"^/(intelligence|finance|rag|ai)/", "public")
_add("POST", r"^/v1/", "public")


def rule_for(method: str, path: str) -> Rule:
    write = method in ("POST", "PUT", "PATCH", "DELETE")
    for methods, rx, rule in _RULES:
        if methods == "*" or methods == method or (methods == W and write):
            if rx.match(path):
                return rule
    return "admin" if write else "none"


def client_ip(scope: Dict[str, Any], headers: Dict[str, str]) -> str:
    """The caller's address; X-Forwarded-For only when PORTAL_TRUST_PROXY says a proxy sets it."""
    if portal_env.TRUST_PROXY and headers.get("x-forwarded-for"):
        return headers["x-forwarded-for"].split(",")[0].strip()
    return (scope.get("client") or ("?",))[0]


def mcp_allowed(user: Optional[Dict[str, Any]], token: Optional[str], scope: Dict[str, Any], headers: Dict[str, str]) -> bool:
    """MCP exposes every portal tool, so it needs: the static PORTAL_MCP_TOKEN, or a super_admin /
    admin session token — or, in development with no token configured, a local client (loopback
    address and no browser Origin header, so a web page can't reach it)."""
    if portal_env.MCP_TOKEN and token and hmac.compare_digest(token, portal_env.MCP_TOKEN):
        return True
    if user and set(user.get("roles") or [user.get("role")]) & ADMIN_ROLES:
        return True
    if not portal_env.MCP_TOKEN and portal_env.MCP_LOCAL and not portal_env.PRODUCTION:
        ip = (scope.get("client") or ("",))[0]
        return ip in ("127.0.0.1", "::1", "localhost") and not headers.get("origin")
    return False


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
            if int(headers.get("content-length") or 0) > portal_env.MAX_BODY_BYTES:
                await _deny(send, 413, "Request body too large")
                return
            if method == "OPTIONS" or rule in ("none",):
                await self.app(scope, receive, send)
                return
            if rule == "docs":
                if portal_env.EXPOSE_DOCS or is_admin(user):
                    await self.app(scope, receive, send)
                else:
                    await _deny(send, 404, "Not Found")
                return
            if rule == "mcp":
                if mcp_allowed(user, token, scope, headers):
                    await self.app(scope, receive, send)
                else:
                    await _deny(send, 401, "MCP needs PORTAL_MCP_TOKEN or an administrator's token (Authorization: Bearer …)",
                                {"WWW-Authenticate": "Bearer"})
                return
            if rule == "public":
                if method == "POST" and path in ("/crm/leads", "/crm/appointments") and not user:
                    if _limited(client_ip(scope, headers)):
                        await _deny(send, 429, "Too many requests — please try again in a minute")
                        return
                await self.app(scope, receive, send)
                return
            if not user:
                await _deny(send, 401, "Please sign in to use this feature", {"WWW-Authenticate": "Bearer"})
                return
            if rule == "admin" and not (set(user.get("roles") or [user.get("role")]) & ADMIN_ROLES):
                await _deny(send, 403, "Only an administrator can do this")
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
