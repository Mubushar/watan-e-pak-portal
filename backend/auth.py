"""
Authentication for the Real Estate Portal
=========================================

Mobile/email accounts with **OTP-verified signup**, password *or* OTP login,
opaque bearer sessions, password reset and an audit trail.

Design notes
------------
* **Delivery.** Codes go out through ``delivery.py`` — SMTP e-mail and SMS via
  Twilio, WhatsApp Cloud API or any HTTP gateway — when those are configured.
  Every message is also written to an in-memory *outbox* (``notifications_db``);
  with nothing configured that outbox is the only "delivery" (status
  ``simulated``), so the whole flow stays testable.
* **OTP is mandatory for signup.** A new account is created in ``pending`` status
  and only becomes ``active`` (and only then can it log in) once a code from the
  signup challenge is verified.
* **Identifiers.** A user may have an email, a mobile number, or both. Mobiles are
  normalised to E.164 (a bare ``03xx…`` Pakistani number becomes ``+923xx…``).
* **Secrets.** Passwords use PBKDF2-HMAC-SHA256 with a per-user salt; OTPs and
  session tokens are random. Codes are stored as salted hashes — the plaintext is
  only retained (and returned as ``dev_otp``) for channels that are *simulated*,
  or whenever ``PORTAL_AUTH_EXPOSE_OTP`` explicitly says so.

This module holds no MCP or FastAPI code; ``server.py`` exposes it over MCP and
``api.py`` reuses the very same functions over REST.
"""

import hashlib
import hmac
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

import delivery
import portal_env


# ============================================================
# CONFIGURATION  (env-overridable, edit here for defaults)
# ============================================================


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off", "")


AUTH_CONFIG: Dict[str, Any] = {
    # OTP
    "otp_length": 6,
    "otp_ttl_seconds": 300,              # 5 minutes
    "otp_max_attempts": 5,
    "otp_resend_cooldown_seconds": 30,
    "otp_max_per_hour": 10,
    "otp_purposes": ["signup", "login", "reset_password"],
    # Sessions
    "session_ttl_hours": 24,
    # Passwords
    "password_min_length": 8,
    # New hashes use this many PBKDF2-SHA256 rounds (OWASP 2023: 600k); older hashes keep the
    # count they were made with (stored with the salt) and still verify.
    "pbkdf2_iterations": int(os.environ.get("PORTAL_PBKDF2_ITERATIONS") or 600_000),
    # Dev convenience: keep the plaintext OTP and return it in responses. Off in production; in
    # development, codes are exposed only for channels with no real provider.
    "expose_otp": _env_bool("PORTAL_AUTH_EXPOSE_OTP", not portal_env.PRODUCTION),
    # Brute-force protection: this many failed sign-ins for one account within the window locks
    # password sign-in for that account for the window.
    "login_max_failures": int(os.environ.get("PORTAL_LOGIN_MAX_FAILURES") or 5),
    "login_lock_minutes": int(os.environ.get("PORTAL_LOGIN_LOCK_MINUTES") or 15),
    # Channels
    "channels": ["sms", "email"],
    "default_country_code": "+92",
}

USER_ROLES = [
    "user", "buyer", "tenant", "seller", "landlord", "investor", "agent", "agency_manager",
    "developer", "valuer", "accountant", "finance_manager", "content_editor", "ad_manager",
    "customer_support", "moderator", "auditor", "admin", "super_admin",
]
USER_STATUSES = ["pending", "active", "suspended"]

# Roles a member of the public may pick when self-registering. Everything else is
# granted by an administrator. Staff roles can be *requested* at sign-up: the account starts as
# a plain user with ``requested_role`` set, and an administrator grants it.
SIGNUP_ROLES = ["user", "buyer", "tenant", "seller", "landlord", "investor", "agent", "developer"]
REQUEST_ONLY_ROLES = ["agent", "developer"]

# Portal areas a role belongs to: the public site, client (self-service), staff
# (back-office) and admin (super-user) tiers.
PORTAL_AREAS = ["public", "client", "staff", "admin"]

# resource.action -> human description
PERMISSIONS: Dict[str, str] = {
    "portal.view": "Browse the public portal",
    "portal.publish": "Publish front-page content",
    "listings.view": "View property listings",
    "listings.manage": "Create / edit / withdraw listings",
    "properties.view": "View the property catalogue",
    "properties.manage": "Edit the property catalogue and GIS coordinates",
    "basedata.manage": "Manage base data: cities, housing schemes / societies, blocks and zones",
    "projects.view": "View big projects",
    "projects.manage": "Create / edit big projects and their media",
    "gis.view": "Use maps, layers and spatial analysis",
    "gis.manage": "Create / edit GIS layers, boundaries and zones",
    "poi.manage": "Manage points of interest",
    "aoi.manage": "Manage areas of interest",
    "crm.view": "View the CRM (agents, leads, customers, deals)",
    "crm.manage": "Create / edit CRM records and run the pipeline",
    "accounting.view": "View the ledger, statements and reports",
    "accounting.manage": "Post journals, invoices, payments and budgets",
    "finance.view": "Run ROI / valuation / yield analysis",
    "finance.manage": "Manage finance assumptions and approvals",
    "payments.view": "View payments and rent roll",
    "payments.manage": "Record payments and issue rent invoices",
    "content.view": "View portal content pages and stories",
    "content.manage": "Create / edit portal content, history and stories",
    "ads.view": "View advertising campaigns and performance",
    "ads.manage": "Create / edit advertisements and campaigns",
    "news.manage": "Manage news channels and the ticker",
    "users.view": "View portal users",
    "users.manage": "Create / edit / suspend portal users",
    "roles.manage": "Create and assign roles and permissions",
    "settings.manage": "Change portal / model settings",
    "audit.view": "Read the audit trail",
}

# name -> role definition. ``permissions`` are resource.action strings.
ROLE_CATALOG: Dict[str, Dict[str, Any]] = {
    "super_admin": {
        "label": "Super administrator", "portal_area": "admin", "level": 100, "is_system": True,
        "description": "Unrestricted access to every portal module.",
        "permissions": list(PERMISSIONS),
    },
    "admin": {
        "label": "Administrator", "portal_area": "admin", "level": 90, "is_system": True,
        "description": "Full operational access; cannot change role definitions.",
        "permissions": [p for p in PERMISSIONS if p != "roles.manage"],
    },
    "moderator": {
        "label": "Portal moderator", "portal_area": "admin", "level": 70, "is_system": True,
        "description": "Approves listings, content and advertisements.",
        "permissions": ["portal.view", "portal.publish", "listings.view", "listings.manage",
                        "content.view", "content.manage", "ads.view", "ads.manage",
                        "news.manage", "crm.view"],
    },
    "developer": {
        "label": "Developer / builder", "portal_area": "staff", "level": 60, "is_system": True,
        "description": "Runs schemes and big projects end to end.",
        "permissions": ["portal.view", "listings.view", "listings.manage", "properties.view",
                        "properties.manage", "projects.view", "projects.manage", "gis.view",
                        "poi.manage", "content.view", "ads.view", "finance.view"],
    },
    "agency_manager": {
        "label": "Agency manager", "portal_area": "staff", "level": 58, "is_system": True,
        "description": "Leads an agency team and its listing book.",
        "permissions": ["portal.view", "listings.view", "listings.manage", "properties.view",
                        "crm.view", "crm.manage", "gis.view", "finance.view", "users.view",
                        "content.view"],
    },
    "agent": {
        "label": "Sales agent", "portal_area": "staff", "level": 50, "is_system": True,
        "description": "Works leads, deals and listings.",
        "permissions": ["portal.view", "listings.view", "listings.manage", "properties.view",
                        "crm.view", "crm.manage", "gis.view", "content.view"],
    },
    "valuer": {
        "label": "Valuer / surveyor", "portal_area": "staff", "level": 50, "is_system": True,
        "description": "Produces valuations and spatial analysis.",
        "permissions": ["portal.view", "listings.view", "properties.view", "gis.view", "gis.manage",
                        "aoi.manage", "finance.view"],
    },
    "finance_manager": {
        "label": "Finance manager", "portal_area": "staff", "level": 55, "is_system": True,
        "description": "Owns accounting, payments and financial approvals.",
        "permissions": ["portal.view", "accounting.view", "accounting.manage", "finance.view",
                        "finance.manage", "payments.view", "payments.manage", "audit.view"],
    },
    "accountant": {
        "label": "Accountant", "portal_area": "staff", "level": 45, "is_system": True,
        "description": "Keeps the books, invoices and rent roll.",
        "permissions": ["portal.view", "accounting.view", "accounting.manage", "finance.view",
                        "payments.view", "payments.manage"],
    },
    "content_editor": {
        "label": "Content editor", "portal_area": "staff", "level": 48, "is_system": True,
        "description": "Writes about / services / history / success stories.",
        "permissions": ["portal.view", "portal.publish", "content.view", "content.manage",
                        "news.manage", "ads.view"],
    },
    "ad_manager": {
        "label": "Advertising manager", "portal_area": "staff", "level": 48, "is_system": True,
        "description": "Runs advertiser campaigns and the ad slots.",
        "permissions": ["portal.view", "ads.view", "ads.manage", "content.view", "finance.view"],
    },
    "customer_support": {
        "label": "Customer support", "portal_area": "staff", "level": 40, "is_system": True,
        "description": "Handles enquiries, leads and user questions.",
        "permissions": ["portal.view", "listings.view", "properties.view", "crm.view", "crm.manage",
                        "users.view", "content.view"],
    },
    "auditor": {
        "label": "Auditor", "portal_area": "staff", "level": 65, "is_system": True,
        "description": "Read-only oversight across finance, users and advertising.",
        "permissions": ["portal.view", "accounting.view", "finance.view", "payments.view",
                        "users.view", "ads.view", "audit.view"],
    },
    "investor": {
        "label": "Investor", "portal_area": "client", "level": 30, "is_system": True,
        "description": "Tracks market data, yields and ROI.",
        "permissions": ["portal.view", "listings.view", "properties.view", "gis.view",
                        "content.view", "finance.view"],
    },
    "seller": {
        "label": "Seller / owner", "portal_area": "client", "level": 26, "is_system": True,
        "description": "Lists and manages their own properties.",
        "permissions": ["portal.view", "listings.view", "listings.manage", "properties.view",
                        "content.view"],
    },
    "landlord": {
        "label": "Landlord", "portal_area": "client", "level": 24, "is_system": True,
        "description": "Manages tenancies and rental income.",
        "permissions": ["portal.view", "listings.view", "listings.manage", "properties.view",
                        "finance.view", "payments.view"],
    },
    "buyer": {
        "label": "Buyer", "portal_area": "public", "level": 16, "is_system": True,
        "description": "Browses listings, saves favourites and enquires.",
        "permissions": ["portal.view", "listings.view", "properties.view", "content.view"],
    },
    "tenant": {
        "label": "Tenant", "portal_area": "public", "level": 14, "is_system": True,
        "description": "Searches rentals and manages their tenancy.",
        "permissions": ["portal.view", "listings.view", "content.view", "payments.view"],
    },
    "user": {
        "label": "Registered user", "portal_area": "public", "level": 10, "is_system": True,
        "description": "Default self-service account.",
        "permissions": ["portal.view", "listings.view", "content.view"],
    },
}


# ============================================================
# MODELS
# ============================================================


class User(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: Optional[str] = None
    username: Optional[str] = None  # optional sign-in name (lower-case, no spaces)
    email: Optional[str] = None
    mobile: Optional[str] = None
    password_hash: Optional[str] = None
    password_salt: Optional[str] = None
    role: str = "user"                  # primary role (see ROLE_CATALOG)
    roles: List[str] = Field(default_factory=list)          # all assigned roles
    extra_permissions: List[str] = Field(default_factory=list)  # direct grants
    status: str = "pending"             # pending | active | suspended
    email_verified: bool = False
    mobile_verified: bool = False
    verified: bool = False
    customer_id: Optional[str] = None   # linked CRM customer
    agent_id: Optional[str] = None      # linked CRM agent
    requested_role: Optional[str] = None  # a staff role asked for at sign-up, granted by an admin
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    last_login_at: Optional[datetime] = None


class OtpCode(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    identifier: str
    channel: str = "sms"                # sms | email
    purpose: str = "signup"             # signup | login | reset_password
    user_id: Optional[str] = None
    code_hash: str = ""
    code: Optional[str] = None          # retained only when expose_otp is on
    created_at: datetime = Field(default_factory=datetime.now)
    expires_at: datetime = Field(default_factory=lambda: datetime.now() + timedelta(minutes=5))
    consumed_at: Optional[datetime] = None
    attempts: int = 0
    max_attempts: int = 5

    def is_expired(self) -> bool:
        return datetime.now() > self.expires_at


class SessionToken(BaseModel):
    token: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    user_id: str
    created_at: datetime = Field(default_factory=datetime.now)
    expires_at: datetime = Field(default_factory=lambda: datetime.now() + timedelta(hours=24))
    revoked: bool = False
    last_used_at: Optional[datetime] = None

    def is_valid(self) -> bool:
        return not self.revoked and datetime.now() <= self.expires_at


class Notification(BaseModel):
    """An outbound SMS / e-mail and how it was delivered."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    channel: str = "sms"                # sms | email
    recipient: str = ""
    subject: str = ""
    body: str = ""
    purpose: Optional[str] = None
    otp_id: Optional[str] = None
    status: str = "simulated"           # simulated | sent | failed
    provider: str = "simulated"         # smtp | twilio | whatsapp | webhook | simulated
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)


class AuthEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event: str = ""
    identifier: Optional[str] = None
    user_id: Optional[str] = None
    detail: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)


class Role(BaseModel):
    """A portal role: a named bundle of permissions in one portal area."""

    name: str
    label: str
    description: Optional[str] = None
    portal_area: str = "staff"          # public | client | staff | admin
    level: int = 10
    permissions: List[str] = Field(default_factory=list)
    is_system: bool = False
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


# ============================================================
# IN-MEMORY STORES
# ============================================================

users_db: List[User] = []
roles_db: List[Role] = []
otps_db: List[OtpCode] = []
sessions_db: List[SessionToken] = []
notifications_db: List[Notification] = []
auth_events_db: List[AuthEvent] = []


# ============================================================
# IDENTIFIER + SECRET HELPERS
# ============================================================

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


def normalize_email(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = str(value).strip().lower()
    return v if _EMAIL_RE.match(v) else None


def normalize_mobile(value: Optional[str]) -> Optional[str]:
    """Normalise a phone number to E.164. A local ``03xx…`` number becomes ``+923xx…``."""
    if not value:
        return None
    v = re.sub(r"[^\d+]", "", str(value))
    if v.startswith("00"):
        v = "+" + v[2:]
    if v.startswith("0"):
        v = AUTH_CONFIG["default_country_code"] + v[1:]
    elif not v.startswith("+"):
        v = "+" + v
    digits = v[1:]
    if not digits.isdigit() or not (8 <= len(digits) <= 15):
        return None
    return v


def identifier_kind(value: Optional[str]) -> Optional[str]:
    if normalize_email(value):
        return "email"
    if normalize_mobile(value):
        return "mobile"
    return None


def normalize_identifier(value: Optional[str]) -> Optional[str]:
    return normalize_email(value) or normalize_mobile(value)


def channel_for(value: str) -> str:
    return "email" if normalize_email(value) else "sms"


def _iterations_of(salt: str) -> int:
    """Salts made since Oct 2026 carry their round count ("i600000$…"); older ones used 120k."""
    if salt.startswith("i") and "$" in salt:
        try:
            return int(salt[1:salt.index("$")])
        except ValueError:
            pass
    return 120_000


def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    salt = salt or f"i{int(AUTH_CONFIG['pbkdf2_iterations'])}${secrets.token_hex(16)}"
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), _iterations_of(salt))
    return dk.hex(), salt


def verify_password(password: str, password_hash: Optional[str], salt: Optional[str]) -> bool:
    if not password_hash or not salt:
        return False
    candidate, _ = hash_password(password, salt)
    return hmac.compare_digest(candidate, password_hash)


def _hash_otp(identifier: str, code: str) -> str:
    return hashlib.sha256(f"{identifier}:{code}".encode("utf-8")).hexdigest()


def public_user(user: User) -> Dict[str, Any]:
    data = user.model_dump(mode="json")
    data.pop("password_hash", None)
    data.pop("password_salt", None)
    data["has_password"] = bool(user.password_hash)
    data["identifiers"] = [x for x in (user.email, user.mobile) if x]
    data["roles"] = user_roles(user)
    data["permissions"] = user_permissions(user)
    return data


# ============================================================
# LOOKUPS + AUDIT
# ============================================================


def find_user_by_id(user_id: Optional[str]) -> Optional[User]:
    return next((u for u in users_db if u.id == user_id), None)


def normalize_username(value: Optional[str]) -> Optional[str]:
    v = (value or "").strip().lower()
    return v if re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,31}", v) else None


def find_user(identifier: Optional[str]) -> Optional[User]:
    ident = normalize_identifier(identifier)
    if ident:
        return next((u for u in users_db if u.email == ident or u.mobile == ident), None)
    name = normalize_username(identifier)
    return next((u for u in users_db if name and u.username == name), None) if name else None


def log_event(event: str, identifier: Optional[str] = None, user_id: Optional[str] = None,
              detail: Optional[str] = None) -> AuthEvent:
    ev = AuthEvent(event=event, identifier=identifier, user_id=user_id, detail=detail)
    auth_events_db.append(ev)
    return ev


# ============================================================
# OTP  (issue / deliver / verify)
# ============================================================


def expose_code(channel: str) -> bool:
    """Return plaintext codes in API responses? An explicit PORTAL_AUTH_EXPOSE_OTP wins;
    otherwise only for channels without a real provider (dev / demo)."""
    if os.environ.get("PORTAL_AUTH_EXPOSE_OTP") is not None:
        return bool(AUTH_CONFIG["expose_otp"])
    return bool(AUTH_CONFIG["expose_otp"]) and delivery.provider_for(channel) == "simulated"


_PURPOSE_TEXT = {"signup": "verify your new account", "login": "sign in", "reset_password": "reset your password"}


def _deliver(otp: OtpCode, code: str) -> Notification:
    minutes = int(AUTH_CONFIG["otp_ttl_seconds"]) // 60
    action = _PURPOSE_TEXT.get(otp.purpose, otp.purpose)
    if otp.channel == "email":
        subject = f"{code} is your Arz-e-Pak verification code"
        body = (
            f"Assalam-o-Alaikum,\n\nUse {code} to {action} on Arz-e-Pak. "
            f"The code expires in {minutes} minutes.\n\n"
            "If you didn't request this, you can ignore this e-mail.\n\n— Arz-e-Pak AI Real Estate"
        )
        status, provider, error = delivery.send_email(otp.identifier, subject, body)
    else:
        subject = "Arz-e-Pak"
        body = f"Arz-e-Pak: {code} is your code to {action}. Valid for {minutes} min. Don't share it."
        status, provider, error = delivery.send_sms(otp.identifier, body, code)
    if status == "sent":
        # The real message carried the code; never keep it readable in the outbox.
        body = body.replace(code, "•" * len(code))
        subject = subject.replace(code, "•" * len(code))
    note = Notification(
        channel=otp.channel, recipient=otp.identifier, subject=subject, body=body,
        purpose=otp.purpose, otp_id=otp.id, status=status, provider=provider, error=error,
    )
    notifications_db.append(note)
    if status == "failed":
        log_event("otp_delivery_failed", otp.identifier, otp.user_id, f"{provider}: {error}")
    return note


def create_otp(identifier: str, purpose: str = "signup", user: Optional[User] = None,
               force: bool = False) -> Dict[str, Any]:
    """Issue + 'deliver' an OTP. Returns ``{"otp": OtpCode, "channel": str}`` or ``{"error": …}``."""
    ident = normalize_identifier(identifier)
    if not ident:
        return {"error": "Provide a valid mobile number or email address"}
    if purpose not in AUTH_CONFIG["otp_purposes"]:
        return {"error": f"purpose must be one of {AUTH_CONFIG['otp_purposes']}"}

    now = datetime.now()
    past = [o for o in otps_db if o.identifier == ident and o.purpose == purpose]
    if past and not force:
        last = max(o.created_at for o in past)
        wait = float(AUTH_CONFIG["otp_resend_cooldown_seconds"]) - (now - last).total_seconds()
        if wait > 0:
            return {
                "error": f"Please wait {int(wait) + 1}s before requesting another code",
                "code": "cooldown",
                "retry_after_seconds": int(wait) + 1,
            }
    last_hour = [o for o in past if now - o.created_at <= timedelta(hours=1)]
    if len(last_hour) >= int(AUTH_CONFIG["otp_max_per_hour"]):
        return {"error": "Too many verification codes requested. Try again later.", "code": "rate_limited"}

    length = int(AUTH_CONFIG["otp_length"])
    code = "".join(secrets.choice("0123456789") for _ in range(length))
    otp = OtpCode(
        identifier=ident,
        channel=channel_for(ident),
        purpose=purpose,
        user_id=(user or find_user(ident)).id if (user or find_user(ident)) else None,
        code_hash=_hash_otp(ident, code),
        code=code if expose_code(channel_for(ident)) else None,
        expires_at=now + timedelta(seconds=int(AUTH_CONFIG["otp_ttl_seconds"])),
        max_attempts=int(AUTH_CONFIG["otp_max_attempts"]),
    )
    note = _deliver(otp, code)
    if note.status == "failed":
        how = "e-mail" if otp.channel == "email" else "SMS"
        return {
            "error": f"We couldn't send the code by {how} to {ident} ({note.error}). Please try again later.",
            "code": "delivery_failed",
            "channel": otp.channel,
        }
    otps_db.append(otp)
    log_event("otp_sent", ident, otp.user_id, f"purpose={purpose} channel={otp.channel} via={note.provider}")
    return {"otp": otp, "channel": otp.channel, "delivery": note.status}


def _otp_hint(otp: OtpCode) -> Dict[str, Any]:
    return {
        "sent_to": otp.identifier,
        "channel": otp.channel,
        "expires_at": otp.expires_at.isoformat(),
        "expires_in_seconds": int(AUTH_CONFIG["otp_ttl_seconds"]),
        # "sent" = really delivered; "simulated" = no provider configured for this channel.
        "delivery": "sent" if delivery.provider_for(otp.channel) != "simulated" else "simulated",
        "dev_otp": otp.code,
    }


def verify_otp(identifier: str, code: str, purpose: str = "signup") -> Dict[str, Any]:
    """Check an OTP. On success, activates a signup account and returns a session token."""
    ident = normalize_identifier(identifier)
    if not ident:
        return {"error": "Provide a valid mobile number or email address"}
    pending = [o for o in otps_db if o.identifier == ident and o.purpose == purpose and not o.consumed_at]
    pending.sort(key=lambda o: o.created_at, reverse=True)
    if not pending:
        return {"error": "No pending verification code for this identifier", "code": "no_otp"}

    otp = pending[0]
    if otp.is_expired():
        return {"error": "Code expired — request a new one", "code": "expired"}
    if otp.attempts >= otp.max_attempts:
        log_event("otp_locked", ident, otp.user_id, purpose)
        return {"error": "Too many incorrect attempts — request a new code", "code": "locked"}

    otp.attempts += 1
    if not hmac.compare_digest(otp.code_hash, _hash_otp(ident, str(code).strip())):
        log_event("otp_failed", ident, otp.user_id, f"attempt {otp.attempts}/{otp.max_attempts}")
        return {
            "error": "Incorrect verification code",
            "code": "invalid",
            "attempts_remaining": max(0, otp.max_attempts - otp.attempts),
        }

    otp.consumed_at = datetime.now()
    user = find_user_by_id(otp.user_id) or find_user(ident)
    if user is None:
        return {"error": "Account not found for this code", "code": "no_user"}

    if otp.channel == "email":
        user.email_verified = True
    else:
        user.mobile_verified = True
    if purpose == "signup":
        user.verified = True
        user.status = "active"
        if not user.roles:
            user.roles = [user.role]
    user.updated_at = datetime.now()

    log_event("otp_verified", ident, user.id, purpose)
    result: Dict[str, Any] = {
        "verified": True,
        "purpose": purpose,
        "user": public_user(user),
    }
    if purpose in ("signup", "login"):
        session = issue_token(user)
        result["token"] = session.token
        result["expires_at"] = session.expires_at.isoformat()
        user.last_login_at = datetime.now()
    return result


def resend_otp(identifier: str, purpose: str = "signup") -> Dict[str, Any]:
    user = find_user(identifier)
    if user is None and purpose != "signup":
        log_event("otp_resend_unknown", normalize_identifier(identifier), None, purpose)
    issued = create_otp(identifier, purpose=purpose, user=user)
    if "error" in issued:
        return issued
    return {"sent": True, "purpose": purpose, **_otp_hint(issued["otp"])}


# ============================================================
# SESSIONS
# ============================================================


def issue_token(user: User) -> SessionToken:
    token = SessionToken(
        user_id=user.id,
        expires_at=datetime.now() + timedelta(hours=int(AUTH_CONFIG["session_ttl_hours"])),
    )
    sessions_db.append(token)
    return token


def resolve_token(token: Optional[str]) -> Optional[SessionToken]:
    if not token:
        return None
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    session = next((s for s in sessions_db if s.token == token), None)
    if session and session.is_valid():
        session.last_used_at = datetime.now()
        return session
    return None


def current_user(token: Optional[str]) -> Optional[User]:
    session = resolve_token(token)
    if not session:
        return None
    return find_user_by_id(session.user_id)


def me(token: Optional[str]) -> Dict[str, Any]:
    user = current_user(token)
    if not user:
        return {"authenticated": False, "error": "Invalid or expired token"}
    return {"authenticated": True, "user": public_user(user)}


def logout(token: Optional[str]) -> Dict[str, Any]:
    session = resolve_token(token)
    if not session:
        return {"error": "Invalid or expired token"}
    session.revoked = True
    log_event("logout", None, session.user_id)
    return {"logged_out": True}


def refresh(token: Optional[str]) -> Dict[str, Any]:
    session = resolve_token(token)
    if not session:
        return {"error": "Invalid or expired token"}
    session.revoked = True
    user = find_user_by_id(session.user_id)
    if user is None:
        return {"error": "Account no longer exists"}
    new_session = issue_token(user)
    log_event("token_refreshed", None, user.id)
    return {"token": new_session.token, "expires_at": new_session.expires_at.isoformat(), "user": public_user(user)}


def revoke_all(user_id: str) -> int:
    count = 0
    for s in sessions_db:
        if s.user_id == user_id and not s.revoked:
            s.revoked = True
            count += 1
    return count


# ============================================================
# SIGNUP / LOGIN / PASSWORD
# ============================================================


def signup(email: Optional[str] = None, mobile: Optional[str] = None, password: Optional[str] = None,
           name: Optional[str] = None, role: str = "user") -> Dict[str, Any]:
    email_n = normalize_email(email)
    mobile_n = normalize_mobile(mobile)
    if email and not email_n:
        return {"error": "Invalid email address", "code": "invalid_email"}
    if mobile and not mobile_n:
        return {"error": "Invalid mobile number", "code": "invalid_mobile"}
    if not email_n and not mobile_n:
        return {"error": "Provide an email address and/or a mobile number", "code": "identifier_required"}
    if password is not None and len(password) < int(AUTH_CONFIG["password_min_length"]):
        return {
            "error": f"Password must be at least {AUTH_CONFIG['password_min_length']} characters",
            "code": "weak_password",
        }
    if email_n and find_user(email_n):
        return {"error": "An account with this email already exists", "code": "email_taken"}
    if mobile_n and find_user(mobile_n):
        return {"error": "An account with this mobile number already exists", "code": "mobile_taken"}
    if role not in SIGNUP_ROLES:
        return {"error": f"role must be one of {SIGNUP_ROLES}", "code": "invalid_role"}
    requested = None
    if role in REQUEST_ONLY_ROLES:
        # Staff roles carry CRM / catalogue rights: start as a plain user until an admin grants it.
        requested, role = role, "user"

    password_hash = password_salt = None
    if password:
        password_hash, password_salt = hash_password(password)

    user = User(
        name=name, email=email_n, mobile=mobile_n,
        password_hash=password_hash, password_salt=password_salt,
        role=role, roles=[role], status="pending", verified=False, requested_role=requested,
    )
    users_db.append(user)
    log_event("signup", email_n or mobile_n, user.id, f"role={role}" + (f", requested={requested}" if requested else ""))

    sent: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []
    for ident in [x for x in (email_n, mobile_n) if x]:
        issued = create_otp(ident, purpose="signup", user=user, force=True)
        (sent if "otp" in issued else failures).append(issued)
    if not sent:
        # Nothing could be delivered: undo the pending account so the person can retry.
        users_db.remove(user)
        log_event("signup_rolled_back", email_n or mobile_n, user.id, "verification code not delivered")
        return failures[0] if failures else {"error": "Could not send a verification code", "code": "delivery_failed"}

    return {
        "user": public_user(user),
        "status": user.status,
        "otp_required": True,
        "verification": {
            "sent_to": [s["otp"].identifier for s in sent],
            "channels": [s["channel"] for s in sent],
            "expires_in_seconds": int(AUTH_CONFIG["otp_ttl_seconds"]),
            "delivery": {s["otp"].identifier: s["delivery"] for s in sent},
            "failed": [f.get("error") for f in failures],
            "dev_otp": {s["otp"].identifier: s["otp"].code for s in sent if s["otp"].code} or None,
        },
        "next_step": "Call verify-otp with the identifier and the code to activate the account.",
    }


_login_failures: Dict[str, List[datetime]] = {}
_DUMMY_SALT = f"i{int(AUTH_CONFIG['pbkdf2_iterations'])}$" + "0" * 32


def _locked(ident: str) -> Optional[int]:
    """Minutes left on a sign-in lock for this account, or None."""
    window = timedelta(minutes=int(AUTH_CONFIG["login_lock_minutes"]))
    now = datetime.now()
    recent = [t for t in _login_failures.get(ident, []) if now - t < window]
    _login_failures[ident] = recent
    if len(recent) >= int(AUTH_CONFIG["login_max_failures"]):
        return max(1, int((window - (now - recent[-1])).total_seconds() // 60) + 1)
    return None


def login(identifier: str, password: Optional[str] = None) -> Dict[str, Any]:
    ident = normalize_identifier(identifier) or normalize_username(identifier)
    user = find_user(ident) if ident else None
    if ident and (mins := _locked(ident)):
        log_event("login_blocked", ident, user.id if user else None, "too many failed attempts")
        return {"error": f"Too many failed sign-ins — try again in {mins} minute{'s' if mins != 1 else ''}, or reset your password",
                "code": "locked"}
    if user is None:
        verify_password(password or "", "0" * 64, _DUMMY_SALT)  # same work as a real check: no account probing by timing
        if ident:
            _login_failures.setdefault(ident, []).append(datetime.now())
        log_event("login_failed", ident, None, "unknown identifier")
        return {"error": "Invalid credentials", "code": "invalid_credentials"}
    if user.status == "suspended":
        log_event("login_blocked", ident, user.id, "suspended")
        return {"error": "This account is suspended", "code": "suspended"}
    if not verify_password(password or "", user.password_hash, user.password_salt):
        _login_failures.setdefault(ident, []).append(datetime.now())
        log_event("login_failed", ident, user.id, "bad password")
        return {"error": "Invalid credentials", "code": "invalid_credentials"}
    _login_failures.pop(ident, None)
    if not user.verified:
        issued = create_otp(ident, purpose="signup", user=user)
        result: Dict[str, Any] = {
            "error": "Account not verified — enter the OTP sent at signup",
            "code": "otp_required",
            "otp_required": True,
        }
        if "otp" in issued:
            result.update(_otp_hint(issued["otp"]))
        return result

    session = issue_token(user)
    user.last_login_at = datetime.now()
    log_event("login", ident, user.id)
    return {
        "token": session.token,
        "expires_at": session.expires_at.isoformat(),
        "token_type": "Bearer",
        "user": public_user(user),
    }


def request_login_otp(identifier: str) -> Dict[str, Any]:
    """Start a passwordless (OTP) login. Responses are generic to avoid user enumeration."""
    ident = normalize_identifier(identifier)
    if not ident:
        return {"error": "Provide a valid mobile number or email address"}
    user = find_user(ident)
    if user is None or user.status == "suspended":
        log_event("login_otp_unknown", ident, user.id if user else None)
        return {
            "sent": True,
            "purpose": "login",
            "sent_to": ident,
            "channel": channel_for(ident),
            "note": "If that account exists, a code has been sent.",
        }
    issued = create_otp(ident, purpose="login", user=user)
    if "error" in issued:
        return issued
    log_event("login_otp_requested", ident, user.id)
    return {"sent": True, "purpose": "login", **_otp_hint(issued["otp"])}


def verify_login_otp(identifier: str, code: str) -> Dict[str, Any]:
    return verify_otp(identifier, code, purpose="login")


def request_password_reset(identifier: str) -> Dict[str, Any]:
    ident = normalize_identifier(identifier)
    if not ident:
        return {"error": "Provide a valid mobile number or email address"}
    user = find_user(ident)
    if user is None:
        log_event("reset_requested_unknown", ident)
        return {"sent": True, "purpose": "reset_password", "sent_to": ident,
                "note": "If that account exists, a reset code has been sent."}
    issued = create_otp(ident, purpose="reset_password", user=user)
    if "error" in issued:
        return issued
    log_event("reset_requested", ident, user.id)
    return {"sent": True, "purpose": "reset_password", **_otp_hint(issued["otp"])}


def reset_password(identifier: str, code: str, new_password: str) -> Dict[str, Any]:
    if not new_password or len(new_password) < int(AUTH_CONFIG["password_min_length"]):
        return {"error": f"Password must be at least {AUTH_CONFIG['password_min_length']} characters",
                "code": "weak_password"}
    checked = verify_otp(identifier, code, purpose="reset_password")
    if "error" in checked:
        return checked
    user = find_user(identifier)
    if user is None:
        return {"error": "Account not found", "code": "no_user"}
    user.password_hash, user.password_salt = hash_password(new_password)
    user.updated_at = datetime.now()
    revoked = revoke_all(user.id)
    log_event("password_reset", normalize_identifier(identifier), user.id)
    return {"reset": True, "user": public_user(user), "sessions_revoked": revoked}


def set_password(token: Optional[str], new_password: str, current_password: Optional[str] = None) -> Dict[str, Any]:
    user = current_user(token)
    if user is None:
        return {"error": "Invalid or expired token", "code": "unauthenticated"}
    if not new_password or len(new_password) < int(AUTH_CONFIG["password_min_length"]):
        return {"error": f"Password must be at least {AUTH_CONFIG['password_min_length']} characters",
                "code": "weak_password"}
    if user.password_hash and not verify_password(current_password or "", user.password_hash, user.password_salt):
        return {"error": "Current password is incorrect", "code": "bad_password"}
    user.password_hash, user.password_salt = hash_password(new_password)
    user.updated_at = datetime.now()
    # Sign the account out everywhere else (a changed password must lock out an attacker).
    sessions_db[:] = [x for x in sessions_db if x.user_id != user.id or x.token == token]
    log_event("password_set", None, user.id)
    return {"updated": True, "user": public_user(user)}


# ============================================================
# ACCOUNT MANAGEMENT (admin) + CRM LINKING
# ============================================================


def link_customer(user_id: str, customer_id: str) -> Optional[User]:
    user = find_user_by_id(user_id)
    if user:
        user.customer_id = customer_id
        user.updated_at = datetime.now()
    return user


def link_agent(user_id: str, agent_id: str) -> Optional[User]:
    user = find_user_by_id(user_id)
    if user:
        user.agent_id = agent_id
        user.updated_at = datetime.now()
    return user


def set_status(user_id: str, status: str) -> Dict[str, Any]:
    if status not in USER_STATUSES:
        return {"error": f"status must be one of {USER_STATUSES}"}
    user = find_user_by_id(user_id)
    if user is None:
        return {"error": "User not found"}
    user.status = status
    user.verified = status == "active" or user.verified
    user.updated_at = datetime.now()
    if status == "suspended":
        revoke_all(user.id)
    log_event("status_changed", None, user.id, status)
    return {"user": public_user(user)}


def set_role(user_id: str, role: str) -> Dict[str, Any]:
    """Set a user's single primary role (see also :func:`set_roles` for multi-role)."""
    known = {r.name for r in roles_db} | set(ROLE_CATALOG)
    if role not in known:
        return {"error": f"role must be one of {sorted(known)}"}
    user = find_user_by_id(user_id)
    if user is None:
        return {"error": "User not found"}
    user.role = role
    if role not in user.roles:
        user.roles.append(role)
    user.role = _primary_role(user)
    user.updated_at = datetime.now()
    log_event("role_changed", None, user.id, role)
    return {"user": public_user(user)}


def list_users(role: Optional[str] = None, status: Optional[str] = None) -> List[Dict[str, Any]]:
    users = list(users_db)
    if role:
        users = [u for u in users if u.role == role]
    if status:
        users = [u for u in users if u.status == status]
    return [public_user(u) for u in users]


def list_otps(identifier: Optional[str] = None, purpose: Optional[str] = None,
              include_consumed: bool = False, limit: int = 50) -> List[Dict[str, Any]]:
    otps = list(otps_db)
    ident = normalize_identifier(identifier) if identifier else None
    if ident:
        otps = [o for o in otps if o.identifier == ident]
    if purpose:
        otps = [o for o in otps if o.purpose == purpose]
    if not include_consumed:
        otps = [o for o in otps if not o.consumed_at]
    otps.sort(key=lambda o: o.created_at, reverse=True)
    out = []
    for o in otps[:limit]:
        row = o.model_dump(mode="json")
        row.pop("code_hash", None)
        out.append(row)
    return out


def list_notifications(limit: int = 50, channel: Optional[str] = None) -> List[Dict[str, Any]]:
    notes = [n for n in notifications_db if not channel or n.channel == channel]
    notes.sort(key=lambda n: n.created_at, reverse=True)
    return [n.model_dump(mode="json") for n in notes[:limit]]


def list_events(limit: int = 100) -> List[Dict[str, Any]]:
    events = sorted(auth_events_db, key=lambda e: e.created_at, reverse=True)
    return [e.model_dump(mode="json") for e in events[:limit]]


def get_config() -> Dict[str, Any]:
    cfg = dict(AUTH_CONFIG)
    cfg["user_roles"] = USER_ROLES
    cfg["user_statuses"] = USER_STATUSES
    cfg["users"] = len(users_db)
    cfg["active_sessions"] = sum(1 for s in sessions_db if s.is_valid())
    cfg["pending_otps"] = sum(1 for o in otps_db if not o.consumed_at and not o.is_expired())
    cfg["delivery"] = delivery.summary()
    cfg["demo_accounts"] = demo_accounts()
    cfg["environment"] = portal_env.ENV
    for k in ("users", "active_sessions", "pending_otps"):  # operational counts are not public
        cfg.pop(k, None)
    return cfg


# ============================================================
# ROLES & PERMISSIONS (RBAC)
# ============================================================


def role_permissions(name: Optional[str]) -> List[str]:
    """The permission list for a role (system catalogue or a custom role)."""
    role = get_role(name)
    if role:
        return list(role.permissions)
    if name in ROLE_CATALOG:
        return list(ROLE_CATALOG[name]["permissions"])
    return []


def get_role(name: Optional[str]) -> Optional[Role]:
    if not name:
        return None
    return next((r for r in roles_db if r.name == name), None)


def role_level(name: Optional[str]) -> int:
    role = get_role(name)
    if role:
        return role.level
    return int(ROLE_CATALOG.get(name or "", {}).get("level", 0))


def role_view(role: Role, with_members: bool = True) -> Dict[str, Any]:
    data = role.model_dump(mode="json")
    data["permission_count"] = len(role.permissions)
    if with_members:
        data["members"] = sum(1 for u in users_db if role.name in user_roles(u))
    return data


def list_roles(portal_area: Optional[str] = None) -> List[Dict[str, Any]]:
    rows = list(roles_db)
    if portal_area:
        rows = [r for r in rows if r.portal_area == portal_area]
    rows.sort(key=lambda r: (-r.level, r.name))
    return [role_view(r) for r in rows]


def list_permissions() -> List[Dict[str, Any]]:
    return [{"permission": k, "description": v} for k, v in PERMISSIONS.items()]


def user_roles(user: User) -> List[str]:
    """All effective role names for a user (primary role first, de-duplicated)."""
    names: List[str] = []
    for name in [user.role, *user.roles]:
        if name and name not in names:
            names.append(name)
    known = {r.name for r in roles_db} | set(ROLE_CATALOG)
    return [n for n in names if n in known]


def user_permissions(user: User) -> List[str]:
    """Effective permissions for a user: union of role permissions + direct grants."""
    perms = set(user.extra_permissions)
    for name in user_roles(user):
        perms.update(role_permissions(name))
    return sorted(perms)


def has_permission(user: Optional[User], permission: str) -> bool:
    return bool(user) and permission in user_permissions(user)


def check_permission(user_id: str, permission: str) -> Dict[str, Any]:
    user = find_user_by_id(user_id)
    if user is None:
        return {"error": "User not found"}
    if permission not in PERMISSIONS:
        return {"error": f"Unknown permission: {permission}", "known": list(PERMISSIONS)}
    perms = user_permissions(user)
    return {"user_id": user.id, "permission": permission, "allowed": permission in perms,
            "roles": user_roles(user), "permissions": perms}


def _primary_role(user: User) -> str:
    names = user.roles or [user.role]
    return max(names, key=role_level) if names else "user"


def set_roles(user_id: str, roles: List[str]) -> Dict[str, Any]:
    """Replace a user's full role set (the highest-level role becomes primary)."""
    user = find_user_by_id(user_id)
    if user is None:
        return {"error": "User not found"}
    known = {r.name for r in roles_db} | set(ROLE_CATALOG)
    bad = [r for r in roles or [] if r not in known]
    if bad:
        return {"error": f"Unknown role(s): {bad}", "known": sorted(known)}
    if not roles:
        return {"error": "At least one role is required"}
    user.roles = list(dict.fromkeys(roles))
    user.role = _primary_role(user)
    user.updated_at = datetime.now()
    log_event("roles_set", None, user.id, ",".join(user.roles))
    return {"user": public_user(user)}


def assign_role(user_id: str, role: str) -> Dict[str, Any]:
    """Grant one role to a user."""
    user = find_user_by_id(user_id)
    if user is None:
        return {"error": "User not found"}
    known = {r.name for r in roles_db} | set(ROLE_CATALOG)
    if role not in known:
        return {"error": f"Unknown role: {role}", "known": sorted(known)}
    if role not in user.roles:
        user.roles.append(role)
    user.role = _primary_role(user)
    user.updated_at = datetime.now()
    log_event("role_assigned", None, user.id, role)
    return {"user": public_user(user)}


def revoke_role(user_id: str, role: str) -> Dict[str, Any]:
    """Remove one role from a user (the last role cannot be removed)."""
    user = find_user_by_id(user_id)
    if user is None:
        return {"error": "User not found"}
    remaining = [r for r in user_roles(user) if r != role]
    if not remaining:
        return {"error": "A user must keep at least one role"}
    user.roles = remaining
    user.role = _primary_role(user)
    user.updated_at = datetime.now()
    log_event("role_revoked", None, user.id, role)
    return {"user": public_user(user)}


def grant_permission(user_id: str, permission: str) -> Dict[str, Any]:
    """Grant one extra permission directly to a user."""
    user = find_user_by_id(user_id)
    if user is None:
        return {"error": "User not found"}
    if permission not in PERMISSIONS:
        return {"error": f"Unknown permission: {permission}", "known": list(PERMISSIONS)}
    if permission not in user.extra_permissions:
        user.extra_permissions.append(permission)
    user.updated_at = datetime.now()
    log_event("permission_granted", None, user.id, permission)
    return {"user": public_user(user)}


def revoke_permission(user_id: str, permission: str) -> Dict[str, Any]:
    """Withdraw a directly-granted permission from a user."""
    user = find_user_by_id(user_id)
    if user is None:
        return {"error": "User not found"}
    user.extra_permissions = [p for p in user.extra_permissions if p != permission]
    user.updated_at = datetime.now()
    log_event("permission_revoked", None, user.id, permission)
    return {"user": public_user(user)}


def users_by_role(role: str) -> List[Dict[str, Any]]:
    return [public_user(u) for u in users_db if role in user_roles(u)]


def create_role(name: str, label: str, description: Optional[str] = None,
                portal_area: str = "staff", level: int = 20,
                permissions: Optional[List[str]] = None) -> Dict[str, Any]:
    """Create a custom role."""
    if get_role(name) or name in ROLE_CATALOG:
        return {"error": f"Role already exists: {name}"}
    if portal_area not in PORTAL_AREAS:
        return {"error": f"portal_area must be one of {PORTAL_AREAS}"}
    perms = list(dict.fromkeys(permissions or []))
    bad = [p for p in perms if p not in PERMISSIONS]
    if bad:
        return {"error": f"Unknown permission(s): {bad}", "known": list(PERMISSIONS)}
    role = Role(name=name, label=label, description=description, portal_area=portal_area,
                level=level, permissions=perms, is_system=False)
    roles_db.append(role)
    log_event("role_created", None, None, name)
    return role_view(role)


def update_role(name: str, label: Optional[str] = None, description: Optional[str] = None,
                portal_area: Optional[str] = None, level: Optional[int] = None,
                permissions: Optional[List[str]] = None) -> Dict[str, Any]:
    """Update a role. System roles keep their permission set but may be re-labelled."""
    role = get_role(name)
    if role is None:
        return {"error": f"Role not found: {name}"}
    if portal_area is not None and portal_area not in PORTAL_AREAS:
        return {"error": f"portal_area must be one of {PORTAL_AREAS}"}
    if permissions is not None:
        bad = [p for p in permissions if p not in PERMISSIONS]
        if bad:
            return {"error": f"Unknown permission(s): {bad}", "known": list(PERMISSIONS)}
        if not role.is_system:
            role.permissions = list(dict.fromkeys(permissions))
    if label is not None:
        role.label = label
    if description is not None:
        role.description = description
    if portal_area is not None:
        role.portal_area = portal_area
    if level is not None:
        role.level = level
    role.updated_at = datetime.now()
    log_event("role_updated", None, None, name)
    return role_view(role)


def delete_role(name: str) -> Dict[str, Any]:
    """Delete a custom role (system roles and in-use roles cannot be removed)."""
    role = get_role(name)
    if role is None:
        return {"error": f"Role not found: {name}"}
    if role.is_system:
        return {"error": "System roles cannot be deleted"}
    in_use = [u.id for u in users_db if name in user_roles(u)]
    if in_use:
        return {"error": f"Role is assigned to {len(in_use)} user(s)", "users": in_use}
    roles_db.remove(role)
    log_event("role_deleted", None, None, name)
    return {"deleted": name}


def role_summary() -> Dict[str, Any]:
    """Roles by area, the permission catalogue size, and per-role member counts."""
    by_area: Dict[str, int] = {}
    for r in roles_db:
        by_area[r.portal_area] = by_area.get(r.portal_area, 0) + 1
    return {
        "roles": len(roles_db),
        "custom_roles": sum(1 for r in roles_db if not r.is_system),
        "permissions": len(PERMISSIONS),
        "portal_areas": PORTAL_AREAS,
        "by_area": by_area,
        "members_per_role": {r.name: sum(1 for u in users_db if r.name in user_roles(u))
                             for r in roles_db},
        "signup_roles": SIGNUP_ROLES,
    }


def seed_roles() -> None:
    """Idempotently load the system role catalogue."""
    if roles_db:
        return
    for name, spec in ROLE_CATALOG.items():
        roles_db.append(
            Role(name=name, label=spec["label"], description=spec.get("description"),
                 portal_area=spec.get("portal_area", "staff"), level=int(spec.get("level", 10)),
                 permissions=list(spec.get("permissions", [])), is_system=True)
        )


# ============================================================
# SEED DATA
# ============================================================


DEMO_USERS: List[Dict[str, Any]] = [
    # ---- admin tier ----
    {"name": "Portal Admin", "email": "admin@portal.pk", "mobile": "+923001234567",
     "password": "Admin@12345", "roles": ["super_admin"]},
    {"name": "Rina Auditor", "email": "auditor@portal.pk", "mobile": "+923101234567",
     "password": "Auditor@12345", "roles": ["auditor"]},
    # ---- staff tier ----
    {"name": "Ayesha Khan", "email": "agent@portal.pk", "mobile": "+923011234567",
     "password": "Agent@12345", "roles": ["agent"]},
    {"name": "Hamza Iqbal", "email": "developer@portal.pk", "mobile": "+923031234567",
     "password": "Developer@12345", "roles": ["developer"]},
    {"name": "Faisal Rehman", "email": "finance@portal.pk", "mobile": "+923051234567",
     "password": "Finance@12345", "roles": ["finance_manager", "accountant"]},
    {"name": "Nadia Aslam", "email": "content@portal.pk", "mobile": "+923061234567",
     "password": "Content@12345", "roles": ["content_editor"]},
    {"name": "Omar Sheikh", "email": "ads@portal.pk", "mobile": "+923071234567",
     "password": "Ads@12345", "roles": ["ad_manager"]},
    {"name": "Zara Malik", "email": "valuer@portal.pk", "mobile": "+923081234567",
     "password": "Valuer@12345", "roles": ["valuer"]},
    {"name": "Kamran Ali", "email": "support@portal.pk", "mobile": "+923091234567",
     "password": "Support@12345", "roles": ["customer_support"]},
    # ---- client tier ----
    {"name": "Sana Tariq", "email": "investor@portal.pk", "mobile": "+923041234567",
     "password": "Investor@12345", "roles": ["investor"]},
    {"name": "Imran Yousaf", "email": "landlord@portal.pk", "mobile": "+923111234567",
     "password": "Landlord@12345", "roles": ["landlord"]},
    # ---- public tier ----
    {"name": "Bilal Ahmed", "email": "bilal@example.com", "mobile": "+923021234567",
     "password": "Buyer@12345", "roles": ["buyer"]},
    {"name": "Sara Naveed", "email": "tenant@portal.pk", "mobile": "+923121234567",
     "password": "Tenant@12345", "roles": ["tenant"]},
]


# Demo sign-ins offered on the login page (development only; the passwords are public).
DEMO_LOGIN_LABELS = {"admin@portal.pk": "Super admin", "agent@portal.pk": "Agent", "finance@portal.pk": "Finance",
                     "developer@portal.pk": "Developer", "investor@portal.pk": "Investor", "bilal@example.com": "Buyer",
                     "landlord@portal.pk": "Landlord", "ads@portal.pk": "Ad manager"}


def demo_accounts() -> List[Dict[str, str]]:
    if not portal_env.SEED_DEMO:
        return []
    present = {u.email for u in users_db}
    return [{"label": DEMO_LOGIN_LABELS[d["email"]], "role": d["roles"][0], "name": d["name"], "email": d["email"],
             "password": d["password"]} for d in DEMO_USERS if d["email"] in DEMO_LOGIN_LABELS and d["email"] in present]


def seed_users() -> None:
    """Idempotent demo accounts covering every portal role (documented in the README).
    Only with PORTAL_SEED_DEMO (on in development, off in production): their passwords are public."""
    seed_roles()
    if users_db or not portal_env.SEED_DEMO:
        return

    seeded = DEMO_USERS
    for row in seeded:
        password_hash, salt = hash_password(row["password"])
        roles = list(row["roles"])
        users_db.append(
            User(
                name=row["name"], email=normalize_email(row["email"]), mobile=normalize_mobile(row["mobile"]),
                password_hash=password_hash, password_salt=salt,
                role=max(roles, key=role_level), roles=roles, status="active",
                verified=True, email_verified=True, mobile_verified=True,
            )
        )
    log_event("seed", None, None, f"{len(seeded)} demo users across {len(ROLE_CATALOG)} roles")


def seed_owner() -> Optional[User]:
    """The portal owner's own super-admin account, from the environment (``backend/.env``,
    never committed): ``PORTAL_OWNER_USERNAME`` and ``PORTAL_OWNER_PASSWORD``, optionally
    ``PORTAL_OWNER_EMAIL``, ``PORTAL_OWNER_MOBILE`` and ``PORTAL_OWNER_NAME``. Signs in with the
    username, e-mail or mobile. Re-applied on every start, so changing the password in .env works."""
    username = normalize_username(os.environ.get("PORTAL_OWNER_USERNAME"))
    password = os.environ.get("PORTAL_OWNER_PASSWORD", "")
    if not username or not password:
        return None
    email = normalize_email(os.environ.get("PORTAL_OWNER_EMAIL", ""))
    mobile = normalize_mobile(os.environ.get("PORTAL_OWNER_MOBILE", ""))
    user = next((u for u in users_db if u.username == username), None)
    password_hash, salt = hash_password(password)
    if user is None:
        user = User(username=username, name=os.environ.get("PORTAL_OWNER_NAME") or username.title(),
                    email=email, mobile=mobile, roles=["super_admin"], role="super_admin", status="active",
                    verified=True, email_verified=bool(email), mobile_verified=bool(mobile))
        users_db.append(user)
    user.password_hash, user.password_salt = password_hash, salt
    user.roles, user.role, user.status, user.verified = ["super_admin"], "super_admin", "active", True
    log_event("seed", None, user.id, "owner super-admin account")
    return user


__all__ = [
    "AUTH_CONFIG", "USER_ROLES", "USER_STATUSES", "SIGNUP_ROLES", "PORTAL_AREAS",
    "PERMISSIONS", "ROLE_CATALOG", "User", "Role", "OtpCode", "SessionToken",
    "Notification", "AuthEvent", "users_db", "roles_db", "otps_db", "sessions_db",
    "notifications_db", "auth_events_db",
    "normalize_email", "normalize_mobile", "normalize_identifier", "identifier_kind",
    "hash_password", "verify_password", "public_user", "find_user", "find_user_by_id",
    "create_otp", "verify_otp", "resend_otp", "signup", "login", "request_login_otp",
    "verify_login_otp", "request_password_reset", "reset_password", "set_password",
    "issue_token", "resolve_token", "current_user", "me", "logout", "refresh", "revoke_all",
    "link_customer", "link_agent", "set_status", "set_role", "list_users", "list_otps",
    "list_notifications", "list_events", "get_config", "seed_users", "seed_owner", "normalize_username",
    # RBAC
    "role_permissions", "get_role", "role_level", "role_view", "list_roles", "list_permissions",
    "user_roles", "user_permissions", "has_permission", "check_permission", "set_roles",
    "assign_role", "revoke_role", "grant_permission", "revoke_permission", "users_by_role",
    "create_role", "update_role", "delete_role", "role_summary", "seed_roles",
]
