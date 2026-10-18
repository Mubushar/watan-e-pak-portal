"""
Outbound messages from the CRM — e-mail, SMS and WhatsApp — and which channels are live.

Uses the same settings as account codes (``delivery.py``):

* e-mail    ``PORTAL_SMTP_HOST``, ``_PORT``, ``_USER``, ``_PASSWORD``, ``_FROM``, ``_SECURITY``
* SMS       ``PORTAL_SMS_PROVIDER=twilio`` (``TWILIO_*``) or ``webhook`` (any bulk-SMS gateway,
            ``PORTAL_SMS_WEBHOOK_*``)
* WhatsApp  WhatsApp Business Cloud API: ``WHATSAPP_TOKEN`` and ``WHATSAPP_PHONE_ID``. Free-text
            messages reach people who wrote to the business in the last 24 hours; outside that
            window WhatsApp needs an approved template, named by ``PORTAL_WHATSAPP_CRM_TEMPLATE``
            (one body parameter: the message text).

With a channel not configured, sending is *simulated*: the message is logged on the lead's
timeline exactly as if sent, marked ``simulated``, so the CRM works end to end in testing.
Inbound: ``POST /crm/webhooks/whatsapp`` (verify token ``PORTAL_WHATSAPP_VERIFY_TOKEN``) and
``POST /crm/webhooks/lead`` (website forms, Facebook / Instagram lead ads via Zapier or Make,
property portals) — see ``crm_ai.ingest_lead``.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, Optional

import httpx

import delivery

CHANNELS = ("whatsapp", "email", "sms")


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def normalise_phone(phone: Optional[str]) -> Optional[str]:
    """Pakistani numbers to E.164: 0300-1234567 / 300 1234567 / 923001234567 → +923001234567."""
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if not digits:
        return None
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("0") and len(digits) == 11:
        digits = "92" + digits[1:]
    elif len(digits) == 10 and digits.startswith("3"):
        digits = "92" + digits
    return "+" + digits


def whatsapp_configured() -> bool:
    return bool(_env("WHATSAPP_TOKEN") and _env("WHATSAPP_PHONE_ID"))


def status() -> Dict[str, Any]:
    """Which channels really send (no secrets)."""
    sms = delivery.sms_provider()
    return {
        "email": {"live": delivery.email_provider() == "smtp", "provider": delivery.email_provider(),
                  "setup": "PORTAL_SMTP_HOST / _USER / _PASSWORD / _FROM"},
        "sms": {"live": sms in ("twilio", "webhook"), "provider": sms if sms in ("twilio", "webhook") else "simulated",
                "setup": "PORTAL_SMS_PROVIDER=twilio (TWILIO_*) or webhook (PORTAL_SMS_WEBHOOK_*)"},
        "whatsapp": {"live": whatsapp_configured(), "provider": "whatsapp-cloud" if whatsapp_configured() else "simulated",
                     "template": _env("PORTAL_WHATSAPP_CRM_TEMPLATE") or None,
                     "setup": "WHATSAPP_TOKEN + WHATSAPP_PHONE_ID (Meta WhatsApp Business Cloud API)"},
        "inbound": {
            "lead_webhook": "/crm/webhooks/lead",
            "lead_webhook_secured": bool(_env("PORTAL_CRM_WEBHOOK_SECRET")),
            "whatsapp_webhook": "/crm/webhooks/whatsapp",
            "whatsapp_verify_token_set": bool(_env("PORTAL_WHATSAPP_VERIFY_TOKEN")),
        },
    }


def _whatsapp_text(to: str, body: str) -> Dict[str, Any]:
    version = _env("PORTAL_WHATSAPP_API_VERSION", "v21.0")
    template = _env("PORTAL_WHATSAPP_CRM_TEMPLATE")
    if template:
        payload: Dict[str, Any] = {
            "messaging_product": "whatsapp", "to": to.lstrip("+"), "type": "template",
            "template": {"name": template, "language": {"code": _env("PORTAL_WHATSAPP_CRM_LANG", "en")},
                         "components": [{"type": "body", "parameters": [{"type": "text", "text": body[:1000]}]}]},
        }
    else:
        payload = {"messaging_product": "whatsapp", "to": to.lstrip("+"), "type": "text",
                   "text": {"preview_url": True, "body": body[:4096]}}
    with httpx.Client(timeout=20) as client:
        r = client.post(f"https://graph.facebook.com/{version}/{_env('WHATSAPP_PHONE_ID')}/messages",
                        json=payload, headers={"Authorization": f"Bearer {_env('WHATSAPP_TOKEN')}"})
    if r.status_code >= 400:
        try:
            err = r.json().get("error", {}).get("message") or r.text[:200]
        except ValueError:
            err = r.text[:200]
        return {"status": "failed", "provider": "whatsapp-cloud", "error": err}
    return {"status": "sent", "provider": "whatsapp-cloud", "error": None}


def send(channel: str, to: str, body: str, subject: Optional[str] = None) -> Dict[str, Any]:
    """Send one message. Returns {status: sent | simulated | failed, provider, error, to}."""
    if channel not in CHANNELS:
        return {"status": "failed", "provider": None, "error": f"channel must be one of {CHANNELS}", "to": to}
    if not body.strip():
        return {"status": "failed", "provider": None, "error": "The message is empty", "to": to}
    if channel == "email":
        if not to or "@" not in to:
            return {"status": "failed", "provider": None, "error": "No valid e-mail address", "to": to}
        st, provider, err = delivery.send_email(to, subject or "Arz-e-Pak", body)
        return {"status": st, "provider": provider, "error": err, "to": to}
    phone = normalise_phone(to)
    if not phone or len(phone) < 11:
        return {"status": "failed", "provider": None, "error": "No valid phone number", "to": to}
    if channel == "whatsapp":
        if not whatsapp_configured():
            return {"status": "simulated", "provider": "simulated", "error": None, "to": phone}
        try:
            return {**_whatsapp_text(phone, body), "to": phone}
        except httpx.HTTPError as exc:
            return {"status": "failed", "provider": "whatsapp-cloud", "error": f"{type(exc).__name__}: {exc}", "to": phone}
    # SMS: only real gateways (the "whatsapp" SMS provider sends OTP templates, not free text).
    if delivery.sms_provider() not in ("twilio", "webhook"):
        return {"status": "simulated", "provider": "simulated", "error": None, "to": phone}
    st, provider, err = delivery.send_sms(phone, body, "")
    return {"status": st, "provider": provider, "error": err, "to": phone}
