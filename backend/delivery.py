"""
Outbound delivery for verification codes (e-mail + SMS / WhatsApp)
==================================================================

``auth.py`` calls :func:`send_email` / :func:`send_sms` for every one-time code.
Nothing here is required: with no configuration the message is only written to the
in-memory outbox (status ``"simulated"``), which keeps tests and local demos working.

Configuration (environment variables, or ``backend/.env``)
---------------------------------------------------------
E-mail — any SMTP server (Gmail/Google Workspace app password, Outlook, Zoho,
SendGrid/Mailgun/Brevo SMTP, cPanel mail, ...)::

    PORTAL_SMTP_HOST=smtp.gmail.com
    PORTAL_SMTP_PORT=587                 # 587 = STARTTLS, 465 = implicit TLS
    PORTAL_SMTP_USER=you@example.com
    PORTAL_SMTP_PASSWORD=app-password
    PORTAL_SMTP_FROM="Arz-e-Pak <no-reply@example.com>"   # defaults to the user
    PORTAL_SMTP_SECURITY=starttls        # starttls | ssl | none (default from port)

SMS — pick one provider with ``PORTAL_SMS_PROVIDER``:

* ``twilio``   — ``TWILIO_ACCOUNT_SID``, ``TWILIO_AUTH_TOKEN`` and ``TWILIO_FROM``
  (a sender number / alphanumeric id) or ``TWILIO_MESSAGING_SERVICE_SID``.
* ``whatsapp`` — WhatsApp Business Cloud API: ``WHATSAPP_TOKEN``, ``WHATSAPP_PHONE_ID``
  and an approved *authentication* template ``PORTAL_WHATSAPP_OTP_TEMPLATE``
  (language ``PORTAL_WHATSAPP_OTP_LANG``, default ``en``). Templates with a
  "copy code" button need ``PORTAL_WHATSAPP_OTP_BUTTON=1`` (the default).
* ``webhook``  — any HTTP SMS gateway (e.g. a Pakistani bulk-SMS provider):
  ``PORTAL_SMS_WEBHOOK_URL``, ``PORTAL_SMS_WEBHOOK_METHOD`` (``POST``/``GET``),
  optional ``PORTAL_SMS_WEBHOOK_HEADERS`` (JSON object) and
  ``PORTAL_SMS_WEBHOOK_BODY`` (JSON template). Placeholders ``{to}`` (+9230…),
  ``{to_digits}`` (9230…), ``{to_local}`` (030…), ``{message}`` and ``{code}`` are
  filled in the URL, headers and body.
"""

from __future__ import annotations

import json
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
from typing import Any, Dict, Optional, Tuple
from urllib.parse import quote

import httpx

try:  # python-dotenv ships with the MCP SDK; settings in backend/.env are optional.
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"), override=False)
except Exception:  # pragma: no cover - dotenv missing or unreadable file
    pass

TIMEOUT_SECONDS = 15

#: (status, provider, error) — status is "sent", "simulated" or "failed".
Result = Tuple[str, str, Optional[str]]


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


# ------------------------------------------------------------------ configuration


def email_provider() -> str:
    """``"smtp"`` when an SMTP host is configured, else ``"simulated"``."""
    return "smtp" if _env("PORTAL_SMTP_HOST") else "simulated"


def sms_provider() -> str:
    """The configured SMS provider, or ``"simulated"`` when none (or incomplete)."""
    name = _env("PORTAL_SMS_PROVIDER").lower()
    required = {
        "twilio": ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN"],
        "whatsapp": ["WHATSAPP_TOKEN", "WHATSAPP_PHONE_ID", "PORTAL_WHATSAPP_OTP_TEMPLATE"],
        "webhook": ["PORTAL_SMS_WEBHOOK_URL"],
    }.get(name)
    if not required or any(not _env(k) for k in required):
        return "simulated"
    if name == "twilio" and not (_env("TWILIO_FROM") or _env("TWILIO_MESSAGING_SERVICE_SID")):
        return "simulated"
    return name


def provider_for(channel: str) -> str:
    return email_provider() if channel == "email" else sms_provider()


def summary() -> Dict[str, str]:
    """Which real channels are wired up (safe to expose: no secrets)."""
    return {"email": email_provider(), "sms": sms_provider()}


# ------------------------------------------------------------------ e-mail


def send_email(to: str, subject: str, body: str) -> Result:
    if email_provider() != "smtp":
        return "simulated", "simulated", None
    host = _env("PORTAL_SMTP_HOST")
    port = int(_env("PORTAL_SMTP_PORT", "587") or 587)
    user = _env("PORTAL_SMTP_USER")
    password = os.environ.get("PORTAL_SMTP_PASSWORD", "")
    security = _env("PORTAL_SMTP_SECURITY", "ssl" if port == 465 else "starttls").lower()
    sender = _env("PORTAL_SMTP_FROM") or user
    if not sender:
        return "failed", "smtp", "PORTAL_SMTP_FROM (or PORTAL_SMTP_USER) is not set"
    name, addr = parseaddr(sender)

    msg = EmailMessage()
    msg["From"] = formataddr((name, addr)) if name else addr
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        context = ssl.create_default_context()
        if security == "ssl":
            server: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=TIMEOUT_SECONDS, context=context)
        else:
            server = smtplib.SMTP(host, port, timeout=TIMEOUT_SECONDS)
        with server:
            if security == "starttls":
                server.starttls(context=context)
            if user:
                server.login(user, password)
            server.send_message(msg)
        return "sent", "smtp", None
    except smtplib.SMTPAuthenticationError:
        return "failed", "smtp", "the mail server rejected the SMTP username/password"
    except (smtplib.SMTPException, OSError) as exc:
        return "failed", "smtp", f"{type(exc).__name__}: {exc}"


# ------------------------------------------------------------------ SMS / WhatsApp


def _phone_forms(e164: str) -> Dict[str, str]:
    digits = e164.lstrip("+")
    local = "0" + digits[2:] if digits.startswith("92") else digits
    return {"to": e164, "to_digits": digits, "to_local": local}


def _http_error(resp: httpx.Response) -> str:
    try:
        data = resp.json()
        detail = data.get("message") or (data.get("error") or {}).get("message") or data
    except Exception:
        detail = resp.text[:200]
    return f"HTTP {resp.status_code}: {detail}"


def send_sms(to: str, message: str, code: str) -> Result:
    provider = sms_provider()
    if provider == "simulated":
        return "simulated", "simulated", None
    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
            if provider == "twilio":
                resp = _twilio(client, to, message)
            elif provider == "whatsapp":
                resp = _whatsapp(client, to, code)
            else:
                resp = _webhook(client, to, message, code)
    except httpx.HTTPError as exc:
        return "failed", provider, f"{type(exc).__name__}: {exc}"
    except (ValueError, KeyError) as exc:
        return "failed", provider, f"bad {provider} configuration: {exc}"
    if resp.status_code >= 400:
        return "failed", provider, _http_error(resp)
    return "sent", provider, None


def _twilio(client: httpx.Client, to: str, message: str) -> httpx.Response:
    sid = _env("TWILIO_ACCOUNT_SID")
    data = {"To": to, "Body": message}
    if _env("TWILIO_MESSAGING_SERVICE_SID"):
        data["MessagingServiceSid"] = _env("TWILIO_MESSAGING_SERVICE_SID")
    else:
        data["From"] = _env("TWILIO_FROM")
    return client.post(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
        data=data, auth=(sid, os.environ.get("TWILIO_AUTH_TOKEN", "")),
    )


def _whatsapp(client: httpx.Client, to: str, code: str) -> httpx.Response:
    version = _env("PORTAL_WHATSAPP_API_VERSION", "v21.0")
    components: list[Dict[str, Any]] = [{"type": "body", "parameters": [{"type": "text", "text": code}]}]
    if _env("PORTAL_WHATSAPP_OTP_BUTTON", "1") not in ("0", "false", "no"):
        components.append({"type": "button", "sub_type": "url", "index": "0",
                           "parameters": [{"type": "text", "text": code}]})
    payload = {
        "messaging_product": "whatsapp",
        "to": to.lstrip("+"),
        "type": "template",
        "template": {
            "name": _env("PORTAL_WHATSAPP_OTP_TEMPLATE"),
            "language": {"code": _env("PORTAL_WHATSAPP_OTP_LANG", "en")},
            "components": components,
        },
    }
    return client.post(
        f"https://graph.facebook.com/{version}/{_env('WHATSAPP_PHONE_ID')}/messages",
        json=payload, headers={"Authorization": f"Bearer {os.environ.get('WHATSAPP_TOKEN', '')}"},
    )


def _fill(template: str, values: Dict[str, str], encode: bool = False) -> str:
    for key, val in values.items():
        template = template.replace("{" + key + "}", quote(val, safe="") if encode else val)
    return template


def _webhook(client: httpx.Client, to: str, message: str, code: str) -> httpx.Response:
    values = {**_phone_forms(to), "message": message, "code": code}
    url = _env("PORTAL_SMS_WEBHOOK_URL")
    method = _env("PORTAL_SMS_WEBHOOK_METHOD", "POST").upper()
    headers = {k: _fill(str(v), values) for k, v in json.loads(_env("PORTAL_SMS_WEBHOOK_HEADERS") or "{}").items()}
    if method == "GET":
        return client.get(_fill(url, values, encode=True), headers=headers)
    body_tpl = _env("PORTAL_SMS_WEBHOOK_BODY") or '{"to": "{to}", "message": "{message}"}'
    # Escape values for JSON before substituting them into the template.
    json_safe = {k: json.dumps(v)[1:-1] for k, v in values.items()}
    body = json.loads(_fill(body_tpl, json_safe))
    return client.request(method, _fill(url, values, encode=True), json=body, headers=headers)
