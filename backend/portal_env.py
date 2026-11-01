"""
Deployment mode and security switches, read once from the environment (``backend/.env``).

``PORTAL_ENV``            ``development`` (default) or ``production``. Production turns the safe
                          defaults on: no demo accounts, no one-time codes in API responses, API docs
                          hidden, HSTS, and CORS / allowed hosts must be listed explicitly.
``PORTAL_SEED_DEMO``      seed the 13 demo accounts and sample data users (default: on in
                          development, off in production).
``PORTAL_EXPOSE_DOCS``    serve /docs, /redoc, /openapi.json (default: on in development only).
``PORTAL_MCP_TOKEN``      static bearer token for MCP clients (Claude Desktop, LM Studio …).
``PORTAL_MCP_LOCAL``      in development, let local MCP clients (loopback, no browser Origin) in
                          without a token when no PORTAL_MCP_TOKEN is set (default on).
``PORTAL_TRUST_PROXY``    trust X-Forwarded-For (only behind your own reverse proxy).
``PORTAL_MAX_BODY_MB``    largest request body accepted (default 30).
``PORTAL_ALLOWED_HOSTS``  comma-separated Host names accepted (production; e.g. watanepak.pk,api.watanepak.pk).
"""

from __future__ import annotations

import os

import envfile  # noqa: F401  (loads backend/.env)

ENV = (os.environ.get("PORTAL_ENV") or "development").strip().lower()
PRODUCTION = ENV in ("production", "prod")


def flag(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None or not v.strip():
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def value(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


SEED_DEMO = flag("PORTAL_SEED_DEMO", not PRODUCTION)
EXPOSE_DOCS = flag("PORTAL_EXPOSE_DOCS", not PRODUCTION)
MCP_TOKEN = value("PORTAL_MCP_TOKEN")
MCP_LOCAL = flag("PORTAL_MCP_LOCAL", not PRODUCTION)
TRUST_PROXY = flag("PORTAL_TRUST_PROXY", False) or flag("AI_TRUST_PROXY", False)
MAX_BODY_BYTES = int(float(value("PORTAL_MAX_BODY_MB", "30")) * 1024 * 1024)
ALLOWED_HOSTS = [h.strip() for h in value("PORTAL_ALLOWED_HOSTS").split(",") if h.strip()]
