"""
Real Estate Portal — FastAPI layer
==================================

Exposes the same business logic defined in `server.py` over REST, and mounts the
MCP server at `/mcp` (Streamable HTTP) so a single process serves BOTH protocols
from one shared in-memory data store.

Run:
    uv run python main.py          # -> http://127.0.0.1:8000/docs
    uv run uvicorn api:app --reload

Notes
-----
Every `@mcp.tool()` function in server.py is a normal Python function that
returns a JSON string, so the REST handlers below simply call them and parse
the result. That keeps MCP and REST perfectly in sync — no duplicated logic.
"""

import asyncio
import base64
import gzip
import hashlib
import hmac
import json
import logging
import os
import re
import uuid
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import (Body, Depends, FastAPI, Header, HTTPException, Query, Request, WebSocket,
                     WebSocketDisconnect)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, Response
from pydantic import ValidationError, BaseModel, Field

import server as core
import ads_network
import geo
import gis
import gis_import
import masterplan
import mapread
import mapfind
import cadastre
import web_lookup
import ai_guard
import doc_extract
import directions as routing
import locations
import megaprojects
import roads
import access
import knowledge
import memory as user_memory
import portal_env
import priority
import project_inventory
import seed_media
import prompts
import property_admin
import storage
import basedata
import crm_ai
import crm_channels
import water
import study_area
import openai_voice
import gemini_live
import openai_facade
from openai_facade import router as openai_router

# ------------------------------------------------------------------
# Expose the MCP Streamable HTTP app at exactly /mcp and start its session manager
# (we add its routes directly instead of `mount()` so the path is /mcp, not /mcp/)
#
# Stateless mode is ON by default: this is a tool-only server, and stateless HTTP
# works with clients that do not carry the Mcp-Session-Id header (the common
# "Missing session ID" failure). Set PORTAL_MCP_STATELESS=0 to require sessions.
# ------------------------------------------------------------------

MCP_STATELESS = os.getenv("PORTAL_MCP_STATELESS", "1").strip().lower() not in ("0", "false", "no", "off")

mcp_http_app = core.mcp.streamable_http_app(streamable_http_path="/mcp", stateless_http=MCP_STATELESS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # A mounted sub-app's lifespan is NOT executed by Starlette, so we run the
    # MCP session manager here ourselves.
    # Durable storage: load the database over the seeded sample data (or save the seed on the
    # first run) and keep writing changes in the background; flush once more on shutdown.
    storage_state = storage.start()
    core.ensure_builtin_layers()  # overlays added in a newer version join the saved ones (unpublished)
    core.publish_master_plans_once(storage.instance())  # DHA master plans are attached by default
    if basedata.add_missing_schemes():                     # societies added to the data file since the save
        storage.mark_dirty()
    if core.add_missing_master_plans():                    # master plans (Bahria, societies…) built since the save
        storage.mark_dirty()
    project_inventory.sync()      # project inventories from the data file: new units in, sold ones marked
    seed_media.apply()            # credited photos for cities / schemes that have none yet
    logging.getLogger("portal").info("storage: %s", storage_state)
    try:
        async with core.mcp.session_manager.run():
            yield
    finally:
        storage.stop()


app = FastAPI(
    title="Real Estate Portal API",
    version=core.SERVER_VERSION,
    description="REST + MCP (at /mcp) for the hierarchical real-estate portal.",
    lifespan=lifespan,
)
# Register the MCP HTTP route(s) on this app.
app.router.routes.extend(mcp_http_app.routes)

# Cross-origin access for the portable app (Electron `app://`, Capacitor
# `capacitor://localhost` / `https://localhost`) and any separately hosted UI.
# Auth is a bearer header (no cookies), so a wildcard is safe; set
# PORTAL_CORS_ORIGINS to a comma-separated allow-list to lock it down.
def _resolve_user(token: Optional[str]) -> Optional[Dict[str, Any]]:
    user = core.auth.current_user(token) if token else None
    return core.auth.public_user(user) if user else None


def _owner_of(kind: str, record_id: str) -> Tuple[bool, Optional[str]]:
    """(found, owning CRM agent id) for the agent-sees-own-book check in access.AccessGuard."""
    db, field = {"lead": (core.leads_db, "assigned_agent_id"), "customer": (core.customers_db, "assigned_agent_id"),
                 "deal": (core.deals_db, "agent_id"), "task": (core.tasks_db, "assigned_agent_id")}.get(kind, (None, None))
    rec = next((r for r in db if r.id == record_id), None) if db is not None else None
    return (rec is not None, getattr(rec, field, None) if rec else None)


# Sign-in and roles for /crm, /marketing, /broker, /agents and /messaging (see access.py). Added
# before CORS so that CORS wraps it and 401 / 403 replies still carry CORS headers.
app.add_middleware(access.AccessGuard, resolve_user=_resolve_user, owner_of=_owner_of)


def _link_demo_agent() -> None:
    """The demo agent account (agent@portal.pk) works the seeded CRM agent of the same name."""
    user = core.auth.find_user("agent@portal.pk")
    agent = next((a for a in core.agents_db if user and a.name == user.name), None)
    if user and agent and not user.agent_id:
        core.auth.link_agent(user.id, agent.id)


_link_demo_agent()
basedata.load_seed()  # researched cities & housing schemes (geodata/pk_*_basedata / housing_schemes)


# ------------------------------------------------------------------ base data admin (basedata.manage)

_BASEDATA_TABLES = ("cities", "schemes", "blocks")


def _basedata_table(table: str) -> str:
    if table not in _BASEDATA_TABLES:
        raise HTTPException(status_code=404, detail=f"Unknown table — one of {', '.join(_BASEDATA_TABLES)}")
    return table


@app.get("/admin/basedata", tags=["admin"])
def basedata_overview() -> Any:
    """The base-data tables with their row counts and editable fields."""
    return {"tables": [{"table": t, "count": len(basedata.rows(t)), "fields": basedata.fields(t)} for t in _BASEDATA_TABLES],
            "approval_statuses": basedata.APPROVAL_STATUSES, "development_statuses": basedata.DEVELOPMENT_STATUSES}


@app.get("/admin/basedata/{table}", tags=["admin"])
def basedata_list(table: str, q: Optional[str] = None, city_id: Optional[str] = None, scheme_id: Optional[str] = None) -> Any:
    rows = basedata.rows(_basedata_table(table), q=q, city_id=city_id, scheme_id=scheme_id)
    return {"table": table, "count": len(rows), "rows": rows}


@app.get("/admin/basedata/{table}/{record_id}", tags=["admin"])
def basedata_get(table: str, record_id: str) -> Any:
    row = basedata.get(_basedata_table(table), record_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    return row


@app.post("/admin/basedata/{table}", tags=["admin"], status_code=201)
def basedata_create(table: str, payload: Dict[str, Any]) -> Any:
    try:
        return basedata.create(_basedata_table(table), payload)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()[0].get("msg", "Invalid value"))


@app.put("/admin/basedata/{table}/{record_id}", tags=["admin"])
def basedata_update(table: str, record_id: str, payload: Dict[str, Any]) -> Any:
    try:
        row = basedata.update(_basedata_table(table), record_id, payload)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()[0].get("msg", "Invalid value"))
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    return row


@app.delete("/admin/basedata/{table}/{record_id}", tags=["admin"])
def basedata_delete(table: str, record_id: str) -> Any:
    """Delete a city, scheme or block — refused (409) while schemes, blocks or listings use it."""
    res = basedata.delete(_basedata_table(table), record_id)
    if res.get("error") == "not_found":
        raise HTTPException(status_code=404, detail="Not found")
    if res.get("error") == "blocked":
        parts = ", ".join(f"{v} {k}" for k, v in res["dependents"].items())
        raise HTTPException(status_code=409, detail=f"Still in use by {parts} — move or delete those first")
    return res

# Compress JSON / GeoJSON / HTML over 1 KB (map layers and lists are large).
app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=5)


class SecurityHeaders:
    """Standard browser hardening headers on every response (HSTS in production)."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                names = {k.lower() for k, _ in headers}
                extra = [
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    (b"x-frame-options", b"SAMEORIGIN"),
                    (b"permissions-policy", b"camera=(), payment=(), geolocation=(self), microphone=(self)"),
                    (b"cross-origin-opener-policy", b"same-origin"),
                ]
                ctype = dict(headers).get(b"content-type", b"")
                if ctype.startswith(b"text/html"):
                    extra.append((b"content-security-policy",
                                  b"default-src 'self' https: data: blob: 'unsafe-inline'; object-src 'none'; "
                                  b"base-uri 'self'; frame-ancestors 'self'; form-action 'self'"))
                if portal_env.PRODUCTION:
                    extra.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
                headers += [(k, v) for k, v in extra if k not in names]
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)


app.add_middleware(SecurityHeaders)


class PersistOnWrite:
    """Tell the storage writer that a request may have changed data (it saves a few seconds later)."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http" or scope.get("method") in ("GET", "HEAD", "OPTIONS"):
            await self.app(scope, receive, send)
            return
        try:
            await self.app(scope, receive, send)
        finally:
            storage.mark_dirty()


app.add_middleware(PersistOnWrite)

# CORS: bearer tokens, no cookies — a wildcard is safe in development. In production list the
# portal's own origins (web, Capacitor, Electron) in PORTAL_CORS_ORIGINS; "*" is refused there.
_cors_origins = [o.strip() for o in os.getenv("PORTAL_CORS_ORIGINS", "*" if not portal_env.PRODUCTION else "").split(",") if o.strip()]
if portal_env.PRODUCTION and "*" in _cors_origins:
    _cors_origins = [o for o in _cors_origins if o != "*"]
    logging.getLogger("portal").warning("PORTAL_CORS_ORIGINS='*' ignored in production — list your origins explicitly")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)
# Production: only answer for the portal's own host names (blocks Host-header / DNS-rebinding tricks).
if portal_env.ALLOWED_HOSTS:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=portal_env.ALLOWED_HOSTS + ["localhost", "127.0.0.1"])


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    """Never leak a traceback: log it with an id, return that id."""
    error_id = uuid.uuid4().hex[:10]
    logging.getLogger("portal").exception("Unhandled error %s on %s %s", error_id, request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error", "error_id": error_id})

# OpenAI-compatible facade (/v1/models, /v1/chat/completions, ...)
app.include_router(openai_router)


def j(raw: str) -> Any:
    """Parse the JSON string returned by a server.py business function."""
    return json.loads(raw)


# ------------------------------------------------------------------
# Dual-language + theme resolution for every HTML surface
# ------------------------------------------------------------------


def _resolve_lang(lang: Optional[str], accept_language: Optional[str]) -> str:
    """Explicit ``?lang=`` wins, then ``Accept-Language``, then the default."""
    valid = set(core.gis.language_codes())
    candidates: List[str] = []
    if lang:
        candidates.append(lang)
    if accept_language:
        candidates += [part.split(";")[0].strip() for part in accept_language.split(",")]
    for candidate in candidates:
        code = (candidate or "").split("-")[0].split("_")[0].strip().lower()
        if code in valid:
            return code
    return core.gis.DEFAULT_LANGUAGE


def ui_lang(
    lang: Optional[str] = Query(default=None, description="UI language code, e.g. en or ur"),
    accept_language: Optional[str] = Header(default=None, alias="Accept-Language"),
) -> str:
    """Dependency: resolve the UI language for an HTML response."""
    return _resolve_lang(lang, accept_language)


def ui_theme(theme: Optional[str] = Query(default=None, description="UI theme: auto | light | dark")) -> str:
    """Dependency: resolve the UI theme for an HTML response."""
    return core.gis.normalize_theme(theme)


# ------------------------------------------------------------------
# Request models
# ------------------------------------------------------------------


class PropertyCreate(BaseModel):
    title: str
    price: float
    city_id: str
    description: Optional[str] = None
    use_type: str = "residential"
    category: str = "house"
    scheme_id: Optional[str] = None
    block_zone_area_id: Optional[str] = None
    total_area: Optional[float] = None
    marla_area: Optional[float] = None
    kanal_area: Optional[float] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    featured: bool = False
    agent_id: Optional[str] = None
    amenities: Optional[List[str]] = None


class PropertyUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    use_type: Optional[str] = None
    category: Optional[str] = None
    status: Optional[str] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    marla_area: Optional[float] = None
    kanal_area: Optional[float] = None
    total_area: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    featured: Optional[bool] = None
    amenities: Optional[List[str]] = None


class LeadCreate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    source: str = "website"
    interest_use_type: Optional[str] = None
    interest_category: Optional[str] = None
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    city_id: Optional[str] = None
    scheme_id: Optional[str] = None
    assigned_agent_id: Optional[str] = None
    notes: Optional[str] = None


class DealCreate(BaseModel):
    title: str
    amount: float
    lead_id: Optional[str] = None
    customer_id: Optional[str] = None
    property_id: Optional[str] = None
    agent_id: Optional[str] = None
    stage: str = "prospecting"
    probability: int = 20
    expected_close_date: Optional[str] = None


class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    assigned_agent_id: Optional[str] = None
    related_type: Optional[str] = None
    related_id: Optional[str] = None
    due_date: Optional[str] = None
    priority: str = "medium"


class MemoryStore(BaseModel):
    operation: str
    key: Optional[str] = None
    value: Optional[str] = None


# ------------------------------------------------------------------
# System
# ------------------------------------------------------------------


@app.get("/", tags=["system"])
def root() -> Dict[str, Any]:
    return {
        "service": "Real Estate Portal",
        "version": core.SERVER_VERSION,
        "rest_docs": "/docs",
        "mcp_endpoint": "/mcp",
        "note": "REST and MCP share the same in-memory store.",
    }


@app.get("/health", tags=["system"])
def health() -> Any:
    return j(core.health_check())


@app.get("/info", tags=["system"])
def info() -> Any:
    return j(core.server_info())


@app.get("/fastapi-info", tags=["system"])
def fastapi_info() -> Any:
    return j(core.fastapi_info())


# ------------------------------------------------------------------
# Properties
# ------------------------------------------------------------------


@app.get("/properties", tags=["properties"])
def list_properties(limit: int = 50) -> Any:
    return j(core.search_properties(limit=limit))


@app.get("/search", tags=["properties"])
def search(
    city: Optional[str] = None,
    use_type: Optional[str] = None,
    category: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    bedrooms: Optional[int] = None,
    min_bathrooms: Optional[int] = None,
    min_marla: Optional[float] = None,
    max_marla: Optional[float] = None,
    featured: Optional[bool] = None,
    feature: Optional[str] = None,
    near: Optional[str] = None,
    near_km: float = 2.0,
    near_place: Optional[str] = None,
    limit: int = 20,
) -> Any:
    return j(
        core.search_properties(
            city=city,
            use_type=use_type,
            category=category,
            min_price=min_price,
            max_price=max_price,
            bedrooms=bedrooms,
            min_bathrooms=min_bathrooms,
            feature=feature,
            near=near,
            near_km=near_km,
            near_place=near_place,
            min_marla=min_marla,
            max_marla=max_marla,
            featured=featured,
            limit=limit,
        )
    )


@app.get("/nearby", tags=["properties"])
def nearby(
    lat: float = Query(...),
    lon: float = Query(...),
    radius_km: float = 5.0,
    use_type: Optional[str] = None,
    limit: int = 20,
) -> Any:
    return j(
        core.search_nearby_properties(
            latitude=lat, longitude=lon, radius_km=radius_km, use_type=use_type, limit=limit
        )
    )


@app.get("/places/find", tags=["places"])
def places_find(kind: Optional[str] = None, area: Optional[str] = None, near: Optional[str] = None,
                radius_km: float = 2.0, name: Optional[str] = None, limit: int = 15) -> Any:
    """Find and count places (schools, malls, hospitals, mosques …) in an area or near a place."""
    result = j(core.places_find(kind=kind, area=area, near=near, radius_km=radius_km, name=name, limit=min(limit, 100)))
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])
    return result


@app.get("/areas/profile", tags=["places"])
def areas_profile(area: str) -> Any:
    """Population, development level, facilities and nearby housing areas of an area / society."""
    result = j(core.area_profile(area))
    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])
    return result


# ---- cadastre: land parcels collected on the map (Cadastre tools); the layer starts empty and unpublished

def _cad_manager() -> bool:
    return access.can(access.current(), "gis.manage")


def _cad(result: Dict[str, Any], status: int = 200) -> Any:
    if "error" in result:
        raise HTTPException(status_code=404 if "not found" in result["error"].lower() else 422, detail=result["error"])
    return result


@app.get("/cadastre/parcels", tags=["cadastre"])
def cadastre_parcels(south: Optional[float] = None, west: Optional[float] = None, north: Optional[float] = None,
                     east: Optional[float] = None, q: Optional[str] = None) -> Any:
    """Parcels as GeoJSON (in a view with south/west/north/east, or matching ``q``: parcel / plot / khasra no., mouza …)."""
    if (hidden := _unpublished("builtin:cadastre", {**_EMPTY_FC, "count": 0})) is not None:
        return hidden
    return cadastre.in_view(_cad_manager(), south, west, north, east, q)


@app.get("/cadastre/summary", tags=["cadastre"])
def cadastre_summary() -> Any:
    """Parcel counts by status, land use, society and survey method, and the form's options."""
    return cadastre.summary()


@app.get("/cadastre/export.geojson", tags=["cadastre"])
def cadastre_export() -> Any:
    """Every parcel with all its fields, as a GeoJSON FeatureCollection (GIS managers)."""
    return JSONResponse(cadastre.in_view(True), headers={"Content-Disposition": 'attachment; filename="cadastre_parcels.geojson"'})


@app.get("/cadastre/pin/{pin}", tags=["cadastre"])
def cadastre_pin(pin: str) -> Any:
    """A parcel PIN (XXXXX-XXXXX-XXXXX, optional -NN suffix) → its parcel, or the ~1 m cell it codes. A shorter
    prefix (6 / 8 / 10 / 12 digits) gives the area it covers (~11 km / 1 km / 110 m / 11 m)."""
    if not core.layer_open("builtin:cadastre"):
        return {"parcel_id": None, "area": cadastre.decode_pin(pin), "unpublished": True}
    return _cad(cadastre.find_pin(pin))


@app.get("/cadastre/pin", tags=["cadastre"])
def cadastre_pin_at(lat: float, lon: float) -> Any:
    """The PIN of the ~1 m cell at a point."""
    try:
        return {"pin": cadastre.encode_pin(lat, lon), "cell": cadastre.decode_pin(cadastre.encode_pin(lat, lon))}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.post("/cadastre/check", tags=["cadastre"])
def cadastre_check(payload: Dict[str, Any] = Body(...)) -> Any:
    """Measure an outline and check it (self-crossing, overlaps) without saving."""
    ring = cadastre._clean_ring(payload.get("ring"))
    errors, warnings = cadastre.check(ring, payload.get("id")) if len(ring) >= 3 else (["A parcel needs at least 3 corners."], [])
    pin = None
    if len(ring) >= 3 and not errors:
        try:
            pin = cadastre.assign_pin(ring, payload.get("id"))[0]
        except ValueError as e:
            errors.append(str(e))
    return {"errors": errors, "warnings": warnings, "pin": pin, **(cadastre.measure(ring) if len(ring) >= 3 else {})}


@app.post("/cadastre/parcels", tags=["cadastre"], status_code=201)
def cadastre_create(payload: Dict[str, Any] = Body(...)) -> Any:
    return _cad(cadastre.create(payload))


@app.get("/cadastre/parcels/{parcel_id}", tags=["cadastre"])
def cadastre_get(parcel_id: str) -> Any:
    p = core.cadastre_parcels_db.get(parcel_id)
    if not p or not core.layer_open("builtin:cadastre"):
        raise HTTPException(status_code=404, detail="Parcel not found")
    return cadastre.public(p, _cad_manager())


@app.put("/cadastre/parcels/{parcel_id}", tags=["cadastre"])
def cadastre_update(parcel_id: str, payload: Dict[str, Any] = Body(...)) -> Any:
    return _cad(cadastre.update(parcel_id, payload))


@app.delete("/cadastre/parcels/{parcel_id}", tags=["cadastre"])
def cadastre_delete(parcel_id: str) -> Any:
    return _cad(cadastre.delete(parcel_id))


@app.get("/map/layers", tags=["places"])
def map_layers(q: Optional[str] = None, city: Optional[str] = None, kind: Optional[str] = None,
               lat: Optional[float] = None, lon: Optional[float] = None, limit: int = 60) -> Any:
    """Every layer on the portal's map — master plans (DHA, Bahria Town, housing societies, CDA sectors),
    uploaded GIS layers and their named features, housing societies and mega projects — with counts
    by kind / group / city. Filter by a name ``q``, ``city`` or ``kind``, or sort by distance from
    ``lat, lon``."""
    return mapfind.catalogue(q=q, city=city, kind=kind, lat=lat, lon=lon, limit=limit)


@app.get("/map/read", tags=["places"])
def map_read(south: float, west: float, north: float, east: float, zoom: int = 15,
             plans: Optional[str] = None, gis: Optional[str] = None, overlays: Optional[str] = None) -> Any:
    """Everything inside a map view, for the assistant: master plans (their text and the green areas drawn
    on them), OpenStreetMap places, roads, population, listings, societies, mega projects and GIS layers.
    ``plans`` / ``gis`` / ``overlays`` are the comma-separated layers switched on (omit = all)."""
    split = lambda v: None if v is None else [x for x in v.split(",") if x]  # noqa: E731
    result = mapread.read(south, west, north, east, zoom, plans=split(plans), gis_ids=split(gis), overlays=split(overlays))
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])
    return j(result) if isinstance(result, str) else result


@app.get("/places/map", tags=["places"])
def places_map(listing_id: Optional[str] = None, place: Optional[str] = None, kinds: Optional[str] = None,
               radius_km: float = 2.0, per_kind: int = 3) -> Any:
    """A listing (or a place) with the nearest schools, mosques, parks, malls … for a map card.
    ``kinds`` is comma-separated (default school,mosque,park,mall,hospital)."""
    result = j(core.map_view(listing_id=listing_id, place=place, radius_km=radius_km, per_kind=per_kind,
                             kinds=[k for k in (kinds or "").split(",") if k.strip()] or None))
    if "error" in result:
        raise HTTPException(status_code=404 if "not found" in result["error"].lower() or "find" in result["error"] else 422,
                            detail=result["error"])
    return result


@app.get("/masterplans", tags=["masterplans"])
def masterplans_list() -> Any:
    """The DHA master plans loaded into the portal."""
    return j(core.masterplan_list())


@app.get("/masterplans/search", tags=["masterplans"])
def masterplans_search(q: str, plan: Optional[str] = None, category: Optional[str] = None, limit: int = 20) -> Any:
    """Find text on the master plans (sector / block names, roads, mosques, plot numbers …)."""
    return j(core.masterplan_search(q, plan=plan, category=category, limit=min(limit, 100)))


@app.get("/masterplans/at", tags=["masterplans"])
def masterplans_at(place: Optional[str] = None, listing_id: Optional[str] = None, plan: Optional[str] = None,
                   lat: Optional[float] = None, lon: Optional[float] = None, radius_m: float = 200.0) -> Any:
    """What the master plan shows around a listing, a place or a point."""
    result = j(core.masterplan_at(place=place, listing_id=listing_id, plan=plan, latitude=lat, longitude=lon,
                                  radius_m=min(radius_m, 1500.0)))
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/masterplans/view", tags=["masterplans"])
def masterplans_view(plan: Optional[str] = None, place: Optional[str] = None, listing_id: Optional[str] = None,
                     radius_m: float = 250.0) -> Any:
    """A plan section to show: close-up image URL + map with the plan overlaid."""
    result = j(core.masterplan_view(plan=plan, place=place, listing_id=listing_id, radius_m=radius_m))
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.post("/masterplans/knowledge/refresh", tags=["masterplans"])
async def masterplans_refresh_knowledge(request: Request, plan: Optional[str] = None) -> Any:
    """Collect facts about each phase from the web (OpenAI web search), with sources."""
    if not openai_voice.configured():
        raise HTTPException(status_code=501, detail="Needs OPENAI_API_KEY in backend/.env")
    ai_guard.check(request, "live")
    meta = masterplan.find_plan(plan) if plan else None
    if plan and not meta:
        raise HTTPException(status_code=404, detail=f"No master plan for '{plan}'")
    out = await asyncio.to_thread(masterplan.collect_knowledge, [meta["key"]] if meta else None)
    return {"updated": list(out), "knowledge": out}


@app.get("/masterplans/{key}", tags=["masterplans"])
def masterplans_summary(key: str) -> Any:
    """A phase at a glance: plot sizes, sectors / blocks, roads, facilities, area statement, web facts."""
    result = j(core.masterplan_summary(key))
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/masterplans/{key}/labels.geojson", tags=["masterplans"])
def masterplans_labels(key: str, category: Optional[str] = None) -> Any:
    """The plan's text labels as GeoJSON points (comma-separated ``category`` filter)."""
    meta = masterplan.find_plan(key)
    if not meta:
        raise HTTPException(status_code=404, detail=f"No master plan '{key}'")
    return masterplan.geojson_labels(meta["key"], [c for c in (category or "").split(",") if c] or None)


@app.get("/masterplans/{key}/tiles/{z}/{x}/{y}.png", tags=["masterplans"])
def masterplans_tile(key: str, z: int, x: int, y: int) -> Any:
    """Map tile of the georeferenced plan (transparent where the plan has nothing)."""
    if not re.fullmatch(r"[a-z0-9]+", key):
        raise HTTPException(status_code=404)
    path = masterplan.DIR / key / "tiles" / str(z) / str(x) / f"{y}.png"
    if not path.is_file():
        return Response(status_code=204)
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/masterplans/{key}/snapshot.png", tags=["masterplans"])
async def masterplans_snapshot(key: str, lat: float, lon: float, radius_m: float = 250.0,
                               label: Optional[str] = None) -> Response:
    """A readable close-up of the master plan around a point (PNG), with a marker and scale bar."""
    png = await asyncio.to_thread(masterplan.snapshot, key, lat, lon, max(60.0, min(radius_m, 3000.0)), label)
    if png is None:
        raise HTTPException(status_code=404, detail="That point is not on this master plan.")
    return Response(content=png, media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})


@app.get("/geo/locate", tags=["places"])
def geo_locate(q: str) -> Any:
    """Find a named place or area on the map."""
    return j(core.geo_locate(q))


@app.get("/geo/summary", tags=["places"])
def geo_summary() -> Any:
    """What place / area / population data is loaded."""
    return geo.summary()


# Pakistan-wide reference layers (small files committed in geodata/, see their attribution).
_PK_FILES: Dict[str, Any] = {}


def _pk_file(name: str) -> Any:
    if name not in _PK_FILES:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "geodata", name), encoding="utf-8") as fh:
            _PK_FILES[name] = json.load(fh)
    return _PK_FILES[name]


def _in_geometry(lat: float, lon: float, geom: Dict[str, Any]) -> bool:
    """Point in a GeoJSON (Multi)Polygon (outer rings minus holes)."""
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    for rings in polys:
        outer = [[y, x] for x, y in rings[0]]
        if geo.point_in_ring(lat, lon, outer) and not any(
                geo.point_in_ring(lat, lon, [[y, x] for x, y in hole]) for hole in rings[1:]):
            return True
    return False


def _unpublished(ref: str, empty: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """An empty answer while an admin hasn't published this map overlay (GIS managers still get the data)."""
    if core.layer_open(ref):
        return None
    return {**empty, "unpublished": True, "note": "This map layer is not published yet."}


_EMPTY_FC: Dict[str, Any] = {"type": "FeatureCollection", "features": []}


@app.get("/geo/provinces", tags=["places"])
def geo_provinces() -> Any:
    """Pakistan's provinces and territories as GeoJSON, each with the number of portal listings in it."""
    if (hidden := _unpublished("builtin:provinces", _EMPTY_FC)) is not None:
        return hidden
    data = _pk_file("pk_provinces.geojson")
    points = [(p.latitude, p.longitude) for p in core.properties_db if p.latitude is not None and p.longitude is not None]
    features = []
    for f in data["features"]:
        n = sum(1 for lat, lon in points if _in_geometry(lat, lon, f["geometry"]))
        features.append({**f, "properties": {**f["properties"], "listings": n}})
    return {"type": "FeatureCollection", "attribution": data.get("attribution"), "features": features}


_DISTRICTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "media", "boundaries", "pk_districts.geojson")
_DISTRICTS: Dict[str, Any] = {}


@app.get("/geo/districts", tags=["places"])
def geo_districts(request: Request) -> Any:
    """Pakistan's districts as GeoJSON (OpenStreetMap admin_level 6, built by ``build_districts.py``)
    with English / Urdu name, province, area, a label point and the number of portal listings in each.
    Islamabad Capital Territory, which has no districts, is included as one."""
    if (hidden := _unpublished("builtin:districts", {**_EMPTY_FC, "count": 0})) is not None:
        return hidden
    if not os.path.exists(_DISTRICTS_FILE):
        return {"type": "FeatureCollection", "features": [], "missing": True,
                "hint": "District data not built yet: run build_districts.py (see backend/README.md)."}
    if "data" not in _DISTRICTS:
        with open(_DISTRICTS_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
        for f in _pk_file("pk_provinces.geojson")["features"]:
            if f["properties"]["name"] == "Islamabad Capital Territory":
                data["features"].append({"type": "Feature", "geometry": f["geometry"], "properties": {
                    "name": "Islamabad", "name_ur": f["properties"].get("name_ur") or "اسلام آباد",
                    "province": "Islamabad Capital Territory", "area_km2": 906.5, "label": [33.69, 73.04]}})
        _DISTRICTS["data"] = data
    data = _DISTRICTS["data"]
    points = [(p.latitude, p.longitude) for p in core.properties_db if p.latitude is not None and p.longitude is not None]
    features = [{**f, "properties": {**f["properties"], "listings": sum(1 for la, lo in points if _in_geometry(la, lo, f["geometry"]))}}
                for f in data["features"]]
    return _json_maybe_gzip(request, {"type": "FeatureCollection", "meta": data.get("meta"), "count": len(features), "features": features})


@app.get("/geo/places", tags=["places"])
def geo_places(south: float, west: float, north: float, east: float, categories: Optional[str] = None,
               limit: int = 1500) -> Any:
    """Points of interest (schools, mosques, hospitals, markets, parks, banks …) inside a map's
    visible box, from the portal's OpenStreetMap place data. ``categories`` is comma-separated
    (education, worship, health, shopping, park, bank, restaurant, transport, fuel, government)."""
    if not geo._finite(south, west, north, east) or north < south or east < west:
        raise HTTPException(status_code=400, detail="Give a valid box: south < north, west < east")
    if (hidden := _unpublished("builtin:osm_pois", {"count": 0, "total": 0, "places": []})) is not None:
        return hidden
    if north - south > 1.5 or east - west > 1.5:
        return {"count": 0, "total": 0, "places": [], "note": "Zoom in to see places."}
    cats = [c.strip() for c in (categories or "").split(",") if c.strip()] or None
    rows, total = geo.places_bbox(south, west, north, east, cats, limit=max(1, min(limit, 3000)))
    return {"count": len(rows), "total": total, "places": rows, "attribution": geo.ATTRIBUTION}


@app.get("/geo/suggest", tags=["places"])
def geo_suggest(q: str, limit: int = 8) -> Any:
    """Type-ahead suggestions for the map's search box: cities, housing schemes, listings,
    sectors / societies and places whose names start with what was typed."""
    words = geo.tokens(q)
    if not words or len(" ".join(words)) < 2:
        return {"query": q, "suggestions": []}
    limit = max(1, min(limit, 15))
    scored: List[Tuple[float, Dict[str, Any]]] = []

    def match(name: str) -> float:
        return geo._prefix_score(words, name, geo.tokens(name))

    for c in _pk_file("pk_cities.json")["cities"]:
        s = match(c["name"])
        if s:
            scored.append((s + 2.0, {"type": "city", "label": c["name"], "sub": f"City · {c['province']}",
                                     "lat": c["lat"], "lon": c["lon"], "zoom": 11}))
    for s_ in core.housing_schemes_db:
        s = match(s_.name)
        if s and s_.latitude is not None and s_.longitude is not None:
            scored.append((s + 1.5, {"type": "scheme", "label": s_.name, "sub": f"Housing scheme · {core.city_name(s_.city_id)}",
                                     "lat": s_.latitude, "lon": s_.longitude, "zoom": 14, "id": s_.id}))
    for p_ in core.properties_db:
        s = match(p_.title)
        if s and p_.latitude is not None and p_.longitude is not None:
            scored.append((s + 1.0, {"type": "listing", "label": p_.title, "sub": f"Listing · {core.city_name(p_.city_id)}",
                                     "lat": p_.latitude, "lon": p_.longitude, "zoom": 17, "id": p_.id}))
    scored.sort(key=lambda x: -x[0])
    rows = [r for _, r in scored][:limit]
    if len(rows) < limit:
        rows += geo.suggest_local(q, limit - len(rows))
    return {"query": q, "suggestions": rows}


@app.get("/geo/geocode", tags=["places"])
def geo_geocode(q: str) -> Any:
    """Find an address or place (local data first, then OpenStreetMap's Nominatim, once).
    Used when the search box is submitted without picking a suggestion."""
    loc = geo.locate(q)
    if not loc:
        raise HTTPException(status_code=404, detail=f"Couldn't find '{q}' on the map.")
    box = loc["shape"].box if loc.get("shape") is not None and getattr(loc["shape"], "box", None) else None
    return {"label": loc.get("name"), "sub": loc.get("label") or loc.get("kind"), "lat": loc["lat"], "lon": loc["lon"],
            "bounds": list(box) if box else None, "source": loc.get("source")}


@app.get("/geo/directions", tags=["routing"])
def geo_directions(from_lat: float, from_lon: float, to_lat: float, to_lon: float, mode: str = "drive",
                   alternatives: bool = True) -> Any:
    """Turn-by-turn directions on real roads (car / bike / foot), fastest first with up to two
    alternatives. Driving times include typical city traffic. Falls back to the portal's own
    router when the online routing service is off or unreachable."""
    return routing.directions((from_lat, from_lon), (to_lat, to_lon), mode=mode, alternatives=alternatives)


class StudyAreaRequest(BaseModel):
    kind: str  # circle | rectangle | polygon
    name: Optional[str] = None
    center: Optional[List[float]] = None  # [lat, lon] (circle)
    radius_m: Optional[float] = None  # circle
    bounds: Optional[Dict[str, float]] = None  # {south, west, north, east} (rectangle)
    coordinates: Optional[List[List[float]]] = None  # [[lat, lon], ...] (polygon)
    save: bool = False  # also keep it as an area of interest


@app.post("/geo/study-area", tags=["aoi"])
def geo_study_area(payload: StudyAreaRequest) -> Any:
    """Case-study report for an area drawn on the map: scores & grade, strengths / concerns /
    recommendation, population & development, every facility inside and the nearest of each
    kind, neighbourhoods, listings & price per marla, schemes, DHA master plan, valuation,
    development cost, economic impact, 5-year forecast and news."""
    if payload.save and not access.can(access.current(), "aoi.manage"):
        raise HTTPException(status_code=403, detail="Saving areas of interest needs the aoi.manage permission")
    result = study_area.study(
        payload.kind, name=payload.name, center=tuple(payload.center) if payload.center else None,  # type: ignore[arg-type]
        radius_m=payload.radius_m, bounds=payload.bounds, coordinates=payload.coordinates, save=payload.save)
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])
    return result


def _json_maybe_gzip(request: Request, data: Any) -> Response:
    """JSON, gzipped when the client accepts it (map layers run to ~1 MB of coordinates; gzip cuts ~4-7x)."""
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if "gzip" in request.headers.get("accept-encoding", "") and len(body) > 4096:
        return Response(gzip.compress(body, compresslevel=5), media_type="application/json",
                        headers={"Content-Encoding": "gzip", "Vary": "Accept-Encoding", "Cache-Control": "public, max-age=3600"})
    return Response(body, media_type="application/json")


@app.get("/geo/roads", tags=["places"])
def geo_roads(request: Request, south: float, west: float, north: float, east: float, zoom: int = 8,
              classes: Optional[str] = None) -> Any:
    """Pakistan's main roads in a map view, from OpenStreetMap: motorways, trunk roads / national
    highways, primary and secondary roads (and those under construction), with number, English /
    Urdu name, lanes, speed limit and surface. Detail and classes follow the zoom. Compact rows:
    ``c`` class, ``s`` status, ``r`` number, ``n`` / ``u`` name, ``l`` lanes, ``v`` max speed,
    ``f`` surface, ``p`` [[lat, lon], ...]."""
    if (hidden := _unpublished("builtin:roads", {"count": 0, "roads": []})) is not None:
        return hidden
    data = roads.in_view(south, west, north, east, zoom, classes.split(",") if classes else None)
    return _json_maybe_gzip(request, data)


@app.get("/geo/water", tags=["places"])
def geo_water(request: Request, south: float, west: float, north: float, east: float, zoom: int = 8,
              classes: Optional[str] = None) -> Any:
    """Pakistan's water bodies in a map view, from OpenStreetMap: rivers, canals (lines) and lakes,
    reservoirs, river beds, ponds (areas, with ``a`` = km²), thinned by zoom. Compact rows: ``c``
    class, ``n`` / ``u`` name, ``p`` [[lat, lon], ...]."""
    if (hidden := _unpublished("builtin:water", {"count": 0, "water": []})) is not None:
        return hidden
    data = water.in_view(south, west, north, east, zoom, classes.split(",") if classes else None)
    return _json_maybe_gzip(request, data)


@app.get("/geo/roads/search", tags=["places"])
def geo_roads_search(q: str, limit: int = 20) -> Any:
    """Find a road by number or name (e.g. ``M-2``, ``N-5``, ``GT Road``) with its extent."""
    rows = roads.search(q, limit)
    return {"count": len(rows), "roads": rows}


@app.get("/geo/megaprojects", tags=["places"])
def geo_megaprojects(type: Optional[str] = None, status: Optional[str] = None, province: Optional[str] = None,
                     city: Optional[str] = None, q: Optional[str] = None, format: str = "json") -> Any:
    """Infrastructure & development mega projects that affect real estate — ring roads, motorways,
    expressways, mass transit, rail, new sectors, industrial / economic zones, airports, business
    districts. Filter by ``type`` / ``status`` (comma lists), ``province``, ``city`` or text ``q``;
    ``format=geojson`` returns a FeatureCollection for maps."""
    rows = megaprojects.search(type=type, status=status, province=province, city=city, q=q)
    if format == "geojson":
        if (hidden := _unpublished("builtin:mega_projects", _EMPTY_FC)) is not None:
            return hidden
        return megaprojects.geojson(rows)
    return {"count": len(rows), "note": megaprojects.note(), "types": megaprojects.TYPE_LABELS,
            "statuses": megaprojects.STATUS_LABELS, "projects": rows}


@app.post("/geo/megaprojects", tags=["places"], status_code=201)
def geo_megaproject_create(payload: Dict[str, Any]) -> Any:
    """Add an infrastructure mega project (GIS managers; saved in the database)."""
    try:
        return megaprojects.admin_save(None, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.put("/geo/megaprojects/{project_id}", tags=["places"])
def geo_megaproject_update(project_id: str, payload: Dict[str, Any]) -> Any:
    """Change a mega project — fields and / or geometry (point, line or polygon)."""
    try:
        return megaprojects.admin_save(project_id, payload)
    except KeyError:
        raise HTTPException(status_code=404, detail="Project not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.delete("/geo/megaprojects/{project_id}", tags=["places"])
def geo_megaproject_delete(project_id: str) -> Any:
    try:
        return megaprojects.admin_delete(project_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Project not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/geo/megaprojects/{project_id}/reset", tags=["places"])
def geo_megaproject_reset(project_id: str) -> Any:
    """Undo every admin change to a shipped mega project."""
    try:
        return megaprojects.admin_reset(project_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Not a shipped project")


@app.get("/geo/megaprojects/near", tags=["places"])
def geo_megaprojects_near(lat: float, lon: float, radius_km: float = 0.0) -> Any:
    """Mega projects whose price effect reaches a point (or an area ``radius_km`` around it), strongest first."""
    rows = megaprojects.near(lat, lon, area_radius_km=radius_km)
    return {"count": len(rows), "projects": rows}


@app.get("/geo/megaprojects/{project_id}", tags=["places"])
def geo_megaproject(project_id: str) -> Any:
    p = megaprojects.get(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return megaprojects.summary(p)


@app.get("/geo/cities", tags=["places"])
def geo_cities(min_population: int = 0) -> Any:
    """Pakistan's main cities (name, province, population, position); ``portal`` marks cities with a portal page."""
    if (hidden := _unpublished("builtin:city_names", {"count": 0, "cities": []})) is not None:
        return hidden
    data = _pk_file("pk_cities.json")
    portal = {c.name.lower() for c in core.cities_db}
    rows = [{**c, "portal": c["name"].lower() in portal} for c in data["cities"] if c["population"] >= min_population]
    return {"count": len(rows), "attribution": data.get("attribution"), "cities": rows}


@app.get("/properties/{property_id}/nearby", tags=["properties"])
def property_nearby(property_id: str, radius_km: float = 3.0) -> Any:
    """Closest school, mosque, hospital, mall, park, transport… around a listing."""
    result = j(core.property_nearby(property_id, radius_km=radius_km))
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/properties/{property_id}", tags=["properties"])
def get_property(property_id: str) -> Any:
    result = j(core.get_property_by_id(property_id))
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.post("/properties", tags=["properties"], status_code=201)
def create_property(payload: PropertyCreate) -> Any:
    result = j(core.add_property(**payload.model_dump(exclude_none=True)))
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.put("/properties/{property_id}", tags=["properties"])
def update_property(property_id: str, payload: PropertyUpdate) -> Any:
    result = j(
        core.update_property(property_id, **payload.model_dump(exclude_none=True))
    )
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.delete("/properties/{property_id}", tags=["properties"])
def delete_property(property_id: str) -> Any:
    result = j(core.delete_property(property_id))
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/properties/{property_id}/compare/{other_id}", tags=["properties"])
def compare_properties(property_id: str, other_id: str) -> Any:
    return j(core.get_property_distance(property_id, other_id))


@app.get("/properties/{property_id}/images", tags=["properties"])
def property_images(property_id: str) -> Any:
    return j(core.image_list("property", property_id))


@app.get("/properties/{property_id}/investment", tags=["properties"])
def property_investment(property_id: str) -> Any:
    return j(core.investment_analysis(property_id))


# ------------------------------------------------------------------
# Hierarchy
# ------------------------------------------------------------------


@app.get("/cities", tags=["hierarchy"])
def cities() -> Any:
    return j(core.list_cities())


@app.get("/schemes", tags=["hierarchy"])
def schemes(city: Optional[str] = None) -> Any:
    return j(core.list_schemes(city=city))


@app.get("/hierarchy", tags=["hierarchy"])
def hierarchy() -> Any:
    return j(core.get_hierarchy())


@app.get("/cities/{city}/insights", tags=["hierarchy"])
def city_insights(city: str) -> Any:
    return j(core.market_insights(city))


# ------------------------------------------------------------------
# Big projects
# ------------------------------------------------------------------


@app.get("/bigprojects", tags=["big-projects"])
def bigprojects(city: Optional[str] = None, project_type: Optional[str] = None) -> Any:
    return j(core.list_big_projects(city=city, project_type=project_type))


@app.get("/bigprojects/{project_id}", tags=["big-projects"])
def bigproject(project_id: str) -> Any:
    result = j(core.get_big_project_by_id(project_id))
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/bigprojects/{project_id}/units", tags=["big-projects"])
def bigproject_units(project_id: str, kind: Optional[str] = None, bedrooms: Optional[int] = None,
                     max_price: Optional[float] = None, status: str = "active", limit: int = 500) -> Any:
    """A project's units for sale (its listings), cheapest first: unit code, floor, size, price,
    payment plan. ``status=all`` includes units the developer no longer lists as available."""
    if not core.find_project(project_id):
        raise HTTPException(status_code=404, detail=f"Big project not found: {project_id}")
    return project_inventory.units(project_id, kind=kind, bedrooms=bedrooms, max_price=max_price,
                                   status=status, limit=max(1, min(limit, 1000)))


# ------------------------------------------------------------------
# RAG / memory / units
# ------------------------------------------------------------------


@app.get("/rag/search", tags=["ai"])
def rag_search(query: str, top_k: int = 5) -> Any:
    return j(core.rag_search(query, top_k=top_k))


@app.post("/rag/search", tags=["ai"])
def rag_search_post(payload: Dict[str, Any]) -> Any:
    return j(core.rag_search(payload.get("query", ""), top_k=int(payload.get("top_k", 5))))


class TranscribeRequest(BaseModel):
    audio_base64: str
    mime_type: str = "audio/webm"
    language: Optional[str] = None  # ignored: the language is detected from the audio


class SpeakRequest(BaseModel):
    text: str
    language: Optional[str] = None  # e.g. "ur-PK" or "en-US"; Urdu script is detected anyway


class RealtimeSessionRequest(BaseModel):
    reply_lang: str = "auto"  # "auto" (follow the speaker), "ur" or "en"


@app.get("/ai/capabilities", tags=["ai"])
def ai_capabilities() -> Any:
    """What the assistant can use: the chat model and voice (no secrets).

    ``voice.live_provider`` says which service runs the live conversation: ``openai``
    (Realtime, the default) or ``gemini`` (``VOICE_PROVIDER=gemini``, for testing)."""
    voice = dict(openai_voice.status())
    if gemini_live.active():
        voice.update(realtime=True, realtime_model=gemini_live.MODEL, live_provider="gemini", live_voice=gemini_live.VOICE)
    else:
        voice["live_provider"] = "openai" if voice["realtime"] else None
    upstream = bool(openai_facade.UPSTREAM_BASE_URL)
    return {
        "chat_mode": "upstream" if upstream else "local",
        "chat_provider": openai_facade.UPSTREAM_PROVIDER,
        "chat_model": openai_facade.UPSTREAM_MODEL if upstream else openai_facade._LOCAL_MODEL,
        "transcription": voice["stt"],
        "transcription_model": voice["stt_model"],
        "voice": voice,
    }


@app.get("/ai/tools", tags=["ai"])
def ai_tools() -> Any:
    """The assistant's tools in Chat Completions format (the same ones the live agent gets).

    The app runs the calls itself against this API, so typed chat and voice notes can
    search listings, open details, read the user's listings and draft a listing.
    """
    tools = [*openai_voice.REALTIME_TOOLS, *openai_voice.CHAT_TOOLS]
    return {"tools": [{"type": "function", "function": {k: t[k] for k in ("name", "description", "parameters")}}
                      for t in tools]}


# OpenAI accepts audio files up to 25 MB; base64 adds a third.
MAX_AUDIO_B64 = 25 * 1024 * 1024 * 4 // 3
MAX_SPEAK_CHARS = 4000


@app.post("/ai/transcribe", tags=["ai"])
async def ai_transcribe(payload: TranscribeRequest, request: Request) -> Any:
    """Speech-to-text for voice notes (OpenAI ``OPENAI_TRANSCRIBE_MODEL``; Urdu, English or mixed)."""
    if not openai_voice.configured():
        raise HTTPException(status_code=501, detail="Voice needs OPENAI_API_KEY in backend/.env")
    if len(payload.audio_base64) > MAX_AUDIO_B64:
        raise HTTPException(status_code=413, detail="Recording too long (25 MB max)")
    ai_guard.check(request, "voice")
    try:
        audio = base64.b64decode(payload.audio_base64.split(",")[-1], validate=False)
    except Exception:
        raise HTTPException(status_code=400, detail="audio_base64 is not valid base64")
    if not audio:
        raise HTTPException(status_code=400, detail="Empty audio")
    try:
        text = await asyncio.to_thread(openai_voice.transcribe, audio, payload.mime_type)
    except openai_voice.VoiceError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))
    return {"text": text, "provider": "openai"}


@app.post("/ai/speak", tags=["ai"])
async def ai_speak(payload: SpeakRequest, request: Request) -> Any:
    """Text-to-speech for voice-note replies (OpenAI ``OPENAI_TTS_MODEL`` with ``OPENAI_VOICE`` /
    ``OPENAI_VOICE_ID``). Returns ``{"audio_base64", "mime_type"}``."""
    if not openai_voice.configured():
        raise HTTPException(status_code=501, detail="Voice needs OPENAI_API_KEY in backend/.env")
    if len(payload.text) > MAX_SPEAK_CHARS:
        raise HTTPException(status_code=413, detail=f"Text too long to speak ({MAX_SPEAK_CHARS} characters max)")
    ai_guard.check(request, "voice")
    try:
        audio, mime = await asyncio.to_thread(openai_voice.speak, payload.text, payload.language)
    except openai_voice.VoiceError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))
    return {"audio_base64": base64.b64encode(audio).decode(), "mime_type": mime, "provider": "openai"}


class WebLookupRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=1000)


@app.post("/ai/web-lookup", tags=["ai"])
async def ai_web_lookup(payload: WebLookupRequest, request: Request) -> Any:
    """Answer a factual question from the web (OpenAI web search), with source links."""
    if not openai_voice.configured():
        raise HTTPException(status_code=501, detail="Web lookup needs OPENAI_API_KEY in backend/.env")
    ai_guard.check(request, "chat")
    try:
        return await asyncio.to_thread(web_lookup.lookup, payload.question)
    except (web_lookup.WebLookupError, openai_voice.VoiceError) as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))


class ExtractRequest(BaseModel):
    name: str = Field(default="document", max_length=300)
    # base64 data URL ("data:application/pdf;base64,...") or bare base64; size checked by hand -> 413
    data_url: str


@app.post("/ai/extract", tags=["ai"])
async def ai_extract(payload: ExtractRequest, request: Request) -> Any:
    """Text out of a document attached in the assistant chat, for the app to add to the conversation.

    Reads PDF (``--- page N ---`` per page; scanned PDFs come back with a ``note``), Word
    (.docx), Excel (.xlsx, first sheets, rows tab-separated) and text files (.txt .csv .tsv .md
    .json .geojson .kml .gpx .xml). 15 MB max. Images are not read here: the chat sends them to
    the model directly. Open to guests, rate-limited per caller (``AI_EXTRACT_PER_MINUTE``).

    Returns ``{"name", "kind": "pdf|docx|xlsx|text", "pages", "chars", "text", "truncated", "note"}``
    — ``text`` is the first 24 000 characters, ``chars`` the full length.
    """
    if len(payload.data_url) > doc_extract.max_b64_chars():
        raise HTTPException(status_code=413, detail=doc_extract.too_big_message())
    ai_guard.check(request, "extract")
    name = payload.name.strip() or "document"
    try:
        data, mime = doc_extract.decode_data_url(payload.data_url)
        return await asyncio.to_thread(doc_extract.extract, name, data, mime)
    except doc_extract.ExtractError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))


class AiContextRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    conversation_id: Optional[str] = Field(default=None, max_length=80)
    channel: str = "chat"  # chat | voice
    k: int = Field(default=5, ge=0, le=12)
    record: bool = True     # save the question in the user's conversation memory


class AiTurnRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=8000)
    conversation_id: Optional[str] = Field(default=None, max_length=80)
    role: str = "assistant"


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    k: int = Field(default=6, ge=1, le=20)
    types: Optional[List[str]] = None


class MemoryNote(BaseModel):
    text: str = Field(..., min_length=2, max_length=300)


class MemorySettings(BaseModel):
    enabled: bool


def _me_or_401() -> Dict[str, Any]:
    me = access.current()
    if not me:
        raise HTTPException(status_code=401, detail="Sign in to use your assistant memory")
    return me


@app.post("/ai/context", tags=["ai"])
def ai_context(payload: AiContextRequest) -> Any:
    """Everything the assistant needs for one question, in one fast call: the system prompt
    (one source for every app), the knowledge base hits with numbered citations, what it
    remembers about this user and the last turns of the conversation. Signed-in users' questions
    are remembered (unless they switched memory off); guests get knowledge only."""
    me = access.current()
    uid = me.get("id") if me else None
    hits = knowledge.search(payload.query, k=payload.k) if payload.k else {"results": [], "context": "", "took_ms": 0}
    recent = user_memory.recent(uid, payload.conversation_id) if uid else []
    learned: List[Dict[str, Any]] = []
    if uid and payload.record:
        learned = user_memory.learn(uid, payload.query)
        user_memory.add_turn(uid, "user", payload.query, payload.conversation_id)
    memory_block = user_memory.context(uid, payload.query)
    return {
        "system_prompt": prompts.compose(me, payload.channel, memory_block, hits.get("context", "")),
        "prompt_version": prompts.PROMPT_VERSION,
        # the same blocks on their own, for apps that keep their own base prompt
        "memory_block": memory_block,
        "knowledge_block": hits.get("context", ""),
        "knowledge": {k: hits.get(k) for k in ("results", "filters", "took_ms")},
        "memory": {"enabled": user_memory.enabled(uid), "items": user_memory.recall(uid, payload.query) if uid else [],
                   "learned": learned},
        "recent": recent,
    }


@app.post("/ai/turn", tags=["ai"])
def ai_turn(payload: AiTurnRequest) -> Any:
    """Save the assistant's reply (or a user turn) in the signed-in user's conversation memory."""
    me = _me_or_401()
    turn = user_memory.add_turn(me["id"], payload.role, payload.content, payload.conversation_id)
    return {"saved": turn is not None}


@app.post("/ai/knowledge/search", tags=["ai"])
def ai_knowledge_search(payload: KnowledgeSearchRequest) -> Any:
    """BM25 search over the portal's knowledge (schemes and their approval status, cities, mega
    projects, listings, news, guides) with sources, trust tiers and [n] citation markers."""
    return knowledge.search(payload.query, k=payload.k, types=payload.types)


@app.get("/me/memory", tags=["me"])
def me_memory() -> Any:
    """What the assistant remembers about me (only I can see this)."""
    return user_memory.list_for(_me_or_401()["id"])


@app.post("/me/memory", tags=["me"], status_code=201)
def me_memory_add(payload: MemoryNote) -> Any:
    result = user_memory.remember(_me_or_401()["id"], payload.text)
    if "error" in result:
        raise HTTPException(status_code=409, detail=result["error"])
    return result


@app.delete("/me/memory/{memory_id}", tags=["me"])
def me_memory_delete(memory_id: str) -> Any:
    result = user_memory.forget(_me_or_401()["id"], memory_id)
    if not result["forgotten"]:
        raise HTTPException(status_code=404, detail="No such memory")
    return result


@app.delete("/me/memory", tags=["me"])
def me_memory_clear() -> Any:
    """Forget everything the assistant remembers about me, including recent conversations."""
    return user_memory.forget(_me_or_401()["id"])


@app.put("/me/memory/settings", tags=["me"])
def me_memory_settings(payload: MemorySettings) -> Any:
    return user_memory.set_enabled(_me_or_401()["id"], payload.enabled)


@app.post("/ai/realtime/session", tags=["ai"])
async def ai_realtime_session(payload: RealtimeSessionRequest, request: Request,
                              authorization: Optional[str] = Header(default=None)) -> Any:
    """Start a live voice conversation.

    OpenAI Realtime (default): returns a short-lived ``client_secret`` (10 minutes to
    connect) plus the ``calls_url`` the app posts its WebRTC offer to.
    Gemini Live (``VOICE_PROVIDER=gemini``): returns ``provider: "gemini"``, a single-use
    ephemeral ``token``, the ``ws_url`` and the ``setup`` to send.
    Either way the session carries the assistant's instructions (with the signed-in user's
    name and role when a bearer token is sent), the reply language (``auto`` / ``ur`` /
    ``en``) and the tools the app executes.
    """
    use_gemini = gemini_live.active()
    if not use_gemini and not openai_voice.configured():
        raise HTTPException(status_code=501, detail="The live voice agent needs OPENAI_API_KEY (or VOICE_PROVIDER=gemini with GEMINI_API_KEY) in backend/.env")
    ai_guard.check(request, "live")
    account = core.auth.current_user(_bearer_token(authorization))
    user = core.auth.public_user(account) if account else None
    lang = payload.reply_lang if payload.reply_lang in ("auto", "ur", "en") else "auto"
    if use_gemini:
        try:
            return await asyncio.to_thread(gemini_live.live_session, user, lang)
        except gemini_live.GeminiError as exc:
            raise HTTPException(status_code=exc.status, detail=str(exc))
    try:
        return await asyncio.to_thread(openai_voice.realtime_session, user, lang)
    except openai_voice.VoiceError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))


@app.get("/memory", tags=["memory"])
def memory() -> Any:
    return j(core.get_memory_analytics())


@app.post("/memory", tags=["memory"])
def memory_store(payload: MemoryStore) -> Any:
    return j(core.memory_store(payload.operation, payload.key, payload.value))


@app.get("/units/convert", tags=["units"])
def unit_convert(value: float, from_unit: str, to_unit: str) -> Any:
    result = j(core.convert_area(value, from_unit, to_unit))
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ------------------------------------------------------------------
# CRM
# ------------------------------------------------------------------


@app.get("/crm/dashboard", tags=["crm"])
def crm_dashboard() -> Any:
    mine = access.agent_scope()
    if not mine:
        return j(core.crm_dashboard())
    leads = [x for x in core.leads_db if x.assigned_agent_id == mine]
    deals = [d for d in core.deals_db if d.agent_id == mine]
    tasks = [t for t in core.tasks_db if t.assigned_agent_id == mine]
    by_status: Dict[str, int] = {}
    for x in leads:
        by_status[x.status] = by_status.get(x.status, 0) + 1
    return {
        "agents": 1,
        "leads": {"total": len(leads), "by_status": by_status},
        "customers": sum(1 for c in core.customers_db if c.assigned_agent_id == mine),
        "deals": {"total": len(deals), "open_value": round(sum(d.amount for d in deals if not d.stage.startswith("closed")), 2),
                  "won_value": round(sum(d.amount for d in deals if d.stage == "closed_won"), 2)},
        "tasks": {"total": len(tasks), "open": sum(1 for t in tasks if t.status in ("open", "in_progress"))},
        "appointments": sum(1 for a in core.appointments_db if a.agent_id == mine),
        "properties": len(core.properties_db),
    }


_PUBLIC_AGENT_FIELDS = ("id", "name", "email", "phone", "region", "specialization", "active", "rating")


@app.get("/crm/agents", tags=["crm"])
def crm_agents(active_only: bool = False) -> Any:
    """CRM agents. Visitors (the property page's contact card) get the public contact fields only."""
    data = j(core.crm_list_agents(active_only=active_only))
    if not access.can(access.current(), "crm.view"):
        data["agents"] = [{k: a.get(k) for k in _PUBLIC_AGENT_FIELDS} for a in data.get("agents", [])]
    return data


@app.get("/crm/leads", tags=["crm"])
def crm_leads(
    status: Optional[str] = None,
    agent_id: Optional[str] = None,
    city: Optional[str] = None,
    min_score: Optional[int] = None,
) -> Any:
    agent_id = access.agent_scope() or agent_id
    return j(core.crm_list_leads(status=status, agent_id=agent_id, city=city, min_score=min_score))


@app.post("/crm/leads", tags=["crm"], status_code=201)
def crm_create_lead(payload: LeadCreate) -> Any:
    return j(core.crm_add_lead(**payload.model_dump(exclude_none=True)))


@app.get("/crm/leads/{lead_id}", tags=["crm"])
def crm_get_lead(lead_id: str) -> Any:
    result = j(core.crm_get_lead(lead_id))
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.post("/crm/leads/{lead_id}/convert", tags=["crm"])
def crm_convert_lead(lead_id: str, customer_type: str = "buyer") -> Any:
    result = j(core.crm_convert_lead(lead_id, customer_type=customer_type))
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/crm/customers", tags=["crm"])
def crm_customers(type: Optional[str] = None) -> Any:
    data = j(core.crm_list_customers(type=type))
    if (mine := access.agent_scope()):
        data["customers"] = [c for c in data["customers"] if c.get("assigned_agent_id") == mine]
        data["count"] = len(data["customers"])
    return data


@app.get("/crm/deals", tags=["crm"])
def crm_deals(stage: Optional[str] = None, agent_id: Optional[str] = None) -> Any:
    return j(core.crm_list_deals(stage=stage, agent_id=access.agent_scope() or agent_id))


@app.post("/crm/deals", tags=["crm"], status_code=201)
def crm_create_deal(payload: DealCreate) -> Any:
    result = j(core.crm_create_deal(**payload.model_dump(exclude_none=True)))
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/crm/pipeline", tags=["crm"])
def crm_pipeline() -> Any:
    mine = access.agent_scope()
    if not mine:
        return j(core.crm_pipeline_summary())
    deals = [d for d in core.deals_db if d.agent_id == mine]
    by_stage: Dict[str, Dict[str, Any]] = {}
    for d in deals:
        e = by_stage.setdefault(d.stage, {"count": 0, "value": 0.0, "weighted": 0.0})
        e["count"] += 1
        e["value"] = round(e["value"] + d.amount, 2)
        e["weighted"] = round(e["weighted"] + d.amount * d.probability / 100, 2)
    return {"stages": by_stage, "open_pipeline_value": round(sum(e["value"] for s, e in by_stage.items() if not s.startswith("closed")), 2),
            "won_value": round(by_stage.get("closed_won", {}).get("value", 0.0), 2), "total_deals": len(deals)}


@app.get("/crm/tasks", tags=["crm"])
def crm_tasks(status: Optional[str] = None, agent_id: Optional[str] = None) -> Any:
    return j(core.crm_list_tasks(status=status, agent_id=access.agent_scope() or agent_id))


@app.post("/crm/tasks", tags=["crm"], status_code=201)
def crm_create_task(payload: TaskCreate) -> Any:
    result = j(core.crm_add_task(**payload.model_dump(exclude_none=True)))
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/crm/appointments", tags=["crm"])
def crm_appointments(status: Optional[str] = None) -> Any:
    data = j(core.crm_list_appointments(status=status))
    if (mine := access.agent_scope()):
        data["appointments"] = [a for a in data["appointments"] if a.get("agent_id") == mine]
        data["count"] = len(data["appointments"])
    return data


# ------------------------------------------------------------------
# GIS (base maps, layers, master plans, spatial queries, export)
# ------------------------------------------------------------------


class GeoLayerCreate(BaseModel):
    name: str
    entity_type: str
    entity_id: str
    geojson: Dict[str, Any]
    layer_type: str = "master_plan"
    description: Optional[str] = None
    base_map: Optional[str] = None
    style: Optional[Dict[str, Any]] = None
    z_index: int = 0
    image_url: Optional[str] = None
    source_url: Optional[str] = None
    visible: bool = True
    published: bool = True
    opacity: float = 1.0


class GeoLayerUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    base_map: Optional[str] = None
    visible: Optional[bool] = None
    opacity: Optional[float] = None
    z_index: Optional[int] = None
    style: Optional[Dict[str, Any]] = None
    geojson: Optional[Dict[str, Any]] = None
    layer_type: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    published: Optional[bool] = None
    source_url: Optional[str] = None


class GeoLayerUpload(BaseModel):
    """An uploaded GIS file (GeoJSON, KML, GPX or CSV) to become a layer, or to replace one's geometry."""
    filename: str = Field(..., max_length=200)
    content: Optional[str] = None          # text files
    content_base64: Optional[str] = None   # or the raw file, base64
    name: Optional[str] = Field(default=None, max_length=200)
    layer_type: str = "zone"
    entity_type: str = "city"
    entity_id: str = "pakistan"
    description: Optional[str] = Field(default=None, max_length=2000)
    style: Optional[Dict[str, Any]] = None
    visible: bool = True
    published: bool = True
    source_url: Optional[str] = None
    replace_layer_id: Optional[str] = None  # replace this layer's geometry instead of adding a layer
    dry_run: bool = False                   # read and check the file, save nothing


class MasterPlanCreate(BaseModel):
    entity_type: str
    entity_id: str
    name: str
    north: float
    south: float
    east: float
    west: float
    image_url: Optional[str] = None
    source_url: Optional[str] = None
    base_map: Optional[str] = None
    description: Optional[str] = None
    layer_type: str = "master_plan"
    style: Optional[Dict[str, Any]] = None


class PolygonQuery(BaseModel):
    coordinates: List[List[float]]
    limit: int = 50


@app.get("/gis/base-maps", tags=["gis"])
def gis_base_maps() -> Any:
    return j(core.gis_list_base_maps())


@app.get("/gis/base-maps/{base_map_id}", tags=["gis"])
def gis_base_map(base_map_id: str) -> Any:
    result = j(core.gis_get_base_map(base_map_id))
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/gis/layers", tags=["gis"])
def gis_layers(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    layer_type: Optional[str] = None,
) -> Any:
    return j(core.gis_list_layers(entity_type=entity_type, entity_id=entity_id, layer_type=layer_type,
                                  include_unpublished=access.can(access.current(), "gis.manage")))


@app.post("/gis/layers", tags=["gis"], status_code=201)
def gis_add_layer(payload: GeoLayerCreate) -> Any:
    result = j(core.gis_add_layer(**payload.model_dump(exclude_none=True)))
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/gis/layers/{layer_id}", tags=["gis"])
def gis_get_layer(layer_id: str) -> Any:
    result = j(core.gis_get_layer(layer_id))
    if "error" in result or (result.get("published") is False and not access.can(access.current(), "gis.manage")):
        raise HTTPException(status_code=404, detail=result.get("error") or f"Layer not found: {layer_id}")
    return result


@app.post("/gis/layers/upload", tags=["gis"], status_code=201)
def gis_upload_layer(payload: GeoLayerUpload) -> Any:
    """Upload a GeoJSON / KML / GPX / CSV file as a new layer (or as the new geometry of
    ``replace_layer_id``). ``dry_run`` only reads and checks the file and returns what it found."""
    try:
        collection, stats = gis_import.read(payload.filename, payload.content, payload.content_base64)
    except gis_import.ImportError_ as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if payload.dry_run:
        return {"dry_run": True, "import": stats}
    if payload.replace_layer_id:
        result = j(core.gis_update_layer(payload.replace_layer_id, geojson=collection))
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        layer = gis.find_layer(payload.replace_layer_id)
        if layer:
            layer.source_file = payload.filename
        return {**result, "import": stats, "replaced": True}
    name = payload.name or os.path.splitext(os.path.basename(payload.filename))[0].replace("_", " ").strip() or "Uploaded layer"
    result = j(core.gis_add_layer(
        entity_type=payload.entity_type, entity_id=payload.entity_id, name=name, geojson=collection,
        layer_type=payload.layer_type, description=payload.description, style=payload.style,
        source_url=payload.source_url, visible=payload.visible, published=payload.published, source_file=payload.filename))
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return {**result, "import": stats}


@app.put("/gis/layers/{layer_id}", tags=["gis"])
def gis_update_layer(layer_id: str, payload: GeoLayerUpdate) -> Any:
    result = j(core.gis_update_layer(layer_id, **payload.model_dump(exclude_none=True)))
    if "error" in result:
        raise HTTPException(status_code=404 if "not found" in result["error"].lower() else 400, detail=result["error"])
    return result


@app.delete("/gis/layers/{layer_id}", tags=["gis"])
def gis_delete_layer(layer_id: str) -> Any:
    result = j(core.gis_delete_layer(layer_id))
    if result.get("error"):
        raise HTTPException(status_code=409, detail=result["error"])
    if not result.get("deleted"):
        raise HTTPException(status_code=404, detail=f"Layer not found: {layer_id}")
    return result


class LayerPublish(BaseModel):
    published: bool = True
    ids: Optional[List[str]] = None  # omit for every layer
    scope: str = "all"               # all | builtin | uploaded | master_plans (when ids is omitted)


@app.post("/gis/layers/publish", tags=["gis"])
def gis_publish_layers(payload: LayerPublish) -> Any:
    """Publish (or hide) many map layers at once — e.g. everything on a fresh install."""
    wanted = set(payload.ids or [])

    def in_scope(l: Any) -> bool:
        ref = str(getattr(l, "geojson_ref", "") or "")
        if wanted:
            return l.id in wanted
        return {"builtin": ref.startswith("builtin:"), "master_plans": ref.startswith("masterplan") or
                (l.image_url or "").startswith("/masterplans/") or l.layer_type in ("boundary", "master_plan") and l.entity_type == "scheme",
                "uploaded": not ref}.get(payload.scope, True)

    changed = 0
    for l in gis.GIS_LAYERS:
        if in_scope(l) and l.published != payload.published:
            l.published, l.updated_at = payload.published, datetime.now()
            changed += 1
    return {"changed": changed, "published": payload.published,
            "now_published": sum(1 for l in gis.GIS_LAYERS if l.published), "layers": len(gis.GIS_LAYERS)}


@app.get("/gis/master-plans", tags=["gis"])
def gis_master_plans(entity_type: Optional[str] = None, entity_id: Optional[str] = None) -> Any:
    return j(core.gis_list_master_plans(entity_type=entity_type, entity_id=entity_id))


@app.post("/gis/master-plans", tags=["gis"], status_code=201)
def gis_add_master_plan(payload: MasterPlanCreate) -> Any:
    result = j(core.gis_add_master_plan(**payload.model_dump(exclude_none=True)))
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/gis/properties-in-bounds", tags=["gis"])
def gis_properties_in_bounds(south: float, west: float, north: float, east: float, limit: int = 50) -> Any:
    result = j(core.gis_properties_in_bounds(south=south, west=west, north=north, east=east, limit=limit))
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/gis/properties-in-polygon", tags=["gis"])
def gis_properties_in_polygon(payload: PolygonQuery) -> Any:
    result = j(core.gis_properties_in_polygon(coordinates=payload.coordinates, limit=payload.limit))
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/gis/area", tags=["gis"])
def gis_area(coordinates: str) -> Any:
    """Polygon area. `coordinates` is JSON: [[lat,lon], ...]."""
    try:
        coords = json.loads(coordinates)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid coordinates JSON: {exc}")
    return j(core.gis_polygon_area(coords))


@app.get("/gis/centroid", tags=["gis"])
def gis_centroid(coordinates: str) -> Any:
    """Polygon centroid. `coordinates` is JSON: [[lat,lon], ...]."""
    try:
        coords = json.loads(coordinates)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid coordinates JSON: {exc}")
    return j(core.gis_polygon_centroid(coords))


@app.get("/gis/bearing", tags=["gis"])
def gis_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> Any:
    return j(core.gis_bearing(lat1, lon1, lat2, lon2))


@app.get("/gis/distance-matrix", tags=["gis"])
def gis_distance_matrix(lat: float, lon: float, property_ids: str) -> Any:
    """Distances from a point to properties. `property_ids` is comma-separated."""
    ids = [p.strip() for p in property_ids.split(",") if p.strip()]
    return j(core.gis_distance_matrix(lat, lon, ids))


@app.get("/gis/export/geojson/{entity_type}/{entity_id}", tags=["gis"])
def gis_export_geojson(entity_type: str, entity_id: str) -> Any:
    return j(core.gis_export_geojson(entity_type, entity_id))


@app.get("/gis/export/kml/{entity_type}/{entity_id}", tags=["gis"])
def gis_export_kml(entity_type: str, entity_id: str) -> Response:
    kml = core.gis_export_kml(entity_type, entity_id)
    return Response(
        content=kml,
        media_type="application/vnd.google-earth.kml+xml",
        headers={"Content-Disposition": f'attachment; filename="{entity_type}-{entity_id}.kml"'},
    )


@app.get("/gis/map/{entity_type}/{entity_id}", tags=["gis"], response_class=HTMLResponse)
def gis_entity_map(
    entity_type: str,
    entity_id: str,
    base_map: Optional[str] = None,
    include_properties: bool = True,
    include_news: bool = False,
    lang: str = Depends(ui_lang),
    theme: str = Depends(ui_theme),
) -> HTMLResponse:
    """Interactive Leaflet map with a base-map switcher and the entity's overlays.

    ``include_news=true`` pins a scrolling real-estate news ticker to the top.
    ``lang`` (``en``/``ur``, RTL supported) and ``theme`` (``auto``/``light``/``dark``)
    localise and re-skin the UI; the language also defaults from ``Accept-Language``.
    """
    html = core.gis_map_preview(
        entity_type, entity_id, base_map=base_map, include_properties=include_properties,
        include_news=include_news, lang=lang, theme=theme,
    )
    return HTMLResponse(content=html)


@app.get("/gis/map", tags=["gis"], response_class=HTMLResponse)
def gis_point_map(
    lat: float = Query(..., description="Latitude of the map centre"),
    lon: float = Query(..., description="Longitude of the map centre"),
    zoom: int = 14,
    base_map: Optional[str] = None,
    include_properties: bool = False,
    include_poi: bool = False,
    title: str = "Real Estate Portal",
    lang: str = Depends(ui_lang),
    theme: str = Depends(ui_theme),
) -> HTMLResponse:
    """Interactive Leaflet map centred on a point (all base maps available in the switcher).

    ``include_properties=true`` and ``include_poi=true`` also plot nearby listings and
    points of interest within a 2 km radius. Shares one implementation with the
    ``gis_point_map`` MCP tool.
    """
    html = core.gis_point_map(
        latitude=lat, longitude=lon, zoom=zoom, base_map=base_map,
        include_properties=include_properties, include_poi=include_poi, title=title,
        lang=lang, theme=theme, radius_km=2.0,
    )
    return HTMLResponse(content=html)


# ------------------------------------------------------------------
# GIS analysis (buffers, features, cost, population, economics, reports)
# ------------------------------------------------------------------


class BufferGeometryQuery(BaseModel):
    geometry: Dict[str, Any]
    distance_m: float
    segments: int = 48


class BufferLayerCreate(BaseModel):
    entity_type: str
    entity_id: str
    name: str
    distance_m: float
    source_layer_id: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    coordinates: Optional[List[List[float]]] = None
    style: Optional[Dict[str, Any]] = None
    layer_type: str = "buffer"


class PolygonAnalysisQuery(BaseModel):
    coordinates: List[List[float]]
    name: str = "Custom area"
    total_units: Optional[int] = None


@app.get("/gis/analysis/assumptions", tags=["gis-analysis"])
def gis_assumptions() -> Any:
    return j(core.gis_analysis_assumptions())


@app.post("/gis/buffer", tags=["gis-analysis"])
def gis_buffer(payload: BufferGeometryQuery) -> Any:
    result = j(core.gis_buffer_geometry(payload.geometry, payload.distance_m, payload.segments))
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/gis/buffer/point", tags=["gis-analysis"])
def gis_buffer_point(latitude: float, longitude: float, radius_m: float, segments: int = 72) -> Any:
    result = j(core.gis_buffer_point(latitude, longitude, radius_m, segments))
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/gis/buffers", tags=["gis-analysis"], status_code=201)
def gis_add_buffer(payload: BufferLayerCreate) -> Any:
    result = j(core.gis_add_buffer_layer(**payload.model_dump(exclude_none=True)))
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/gis/ring-analysis", tags=["gis-analysis"])
def gis_ring_analysis(
    lat: float = Query(...),
    lon: float = Query(...),
    radii_km: str = "1,3,5",
    use_type: Optional[str] = None,
) -> Any:
    """Concentric-ring accessibility analysis. `radii_km` is comma-separated."""
    try:
        radii = [float(r) for r in radii_km.split(",") if r.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="radii_km must be comma-separated numbers, e.g. 1,3,5")
    result = j(core.gis_ring_analysis(lat, lon, radii, use_type=use_type))
    if isinstance(result, dict) and "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/gis/polygon-analysis", tags=["gis-analysis"])
def gis_polygon_analysis(payload: PolygonAnalysisQuery) -> Any:
    result = j(core.gis_polygon_analysis(payload.coordinates, payload.name, payload.total_units))
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/gis/analysis/{entity_type}/{entity_id}", tags=["gis-analysis"])
def gis_area_analysis(entity_type: str, entity_id: str) -> Any:
    return j(core.gis_area_analysis(entity_type, entity_id))


@app.get("/gis/analysis/{entity_type}/{entity_id}/cost", tags=["gis-analysis"])
def gis_development_cost(entity_type: str, entity_id: str) -> Any:
    return j(core.gis_development_cost(entity_type, entity_id))


@app.get("/gis/analysis/{entity_type}/{entity_id}/population", tags=["gis-analysis"])
def gis_population_estimate(entity_type: str, entity_id: str) -> Any:
    return j(core.gis_population_estimate(entity_type, entity_id))


@app.get("/gis/analysis/{entity_type}/{entity_id}/economic-impact", tags=["gis-analysis"])
def gis_economic_impact(entity_type: str, entity_id: str) -> Any:
    return j(core.gis_economic_impact(entity_type, entity_id))


@app.get("/gis/features/{scope_type}/{scope_id}", tags=["gis-analysis"])
def gis_feature_table(scope_type: str, scope_id: str, metric: str = "population") -> Any:
    result = j(core.gis_feature_table(scope_type, scope_id, metric))
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/gis/thematic/{scope_type}/{scope_id}", tags=["gis-analysis"], response_class=HTMLResponse)
def gis_thematic_map(
    scope_type: str,
    scope_id: str,
    metric: str = "population",
    palette: str = "blues",
    classes: int = 5,
    base_map: Optional[str] = None,
    lang: str = Depends(ui_lang),
    theme: str = Depends(ui_theme),
) -> HTMLResponse:
    """Choropleth (thematic) map HTML for a metric across a city's schemes or a scheme's blocks."""
    html = core.gis_thematic_map(scope_type, scope_id, metric, palette, classes, base_map, lang=lang, theme=theme)
    return HTMLResponse(content=html)


@app.get("/gis/report/{entity_type}/{entity_id}", tags=["gis-analysis"], response_class=HTMLResponse)
def gis_report(
    entity_type: str,
    entity_id: str,
    include_map: bool = True,
    include_outlook: bool = False,
    include_news: bool = False,
    years: int = 5,
    lang: str = Depends(ui_lang),
    theme: str = Depends(ui_theme),
) -> HTMLResponse:
    """Printable HTML analysis report (area, valuation, population, cost, economics).

    ``include_outlook=true`` adds cost/development + multi-factor predictions;
    ``include_news=true`` embeds the real-estate news ticker.
    """
    html = core.gis_area_report(
        entity_type, entity_id, include_map=include_map,
        include_outlook=include_outlook, include_news=include_news, years=years,
        lang=lang, theme=theme,
    )
    return HTMLResponse(content=html)


@app.get("/gis/analysis/{entity_type}/{entity_id}/cost-development", tags=["gis-analysis"])
def gis_cost_development(entity_type: str, entity_id: str, sale_uplift: float = 0.0, build_years: int = 3) -> Any:
    return j(core.gis_cost_development_analysis(entity_type, entity_id, sale_uplift=sale_uplift, build_years=build_years))


@app.get("/gis/analysis/{entity_type}/{entity_id}/factors", tags=["gis-analysis"])
def gis_market_factors(entity_type: str, entity_id: str) -> Any:
    return j(core.gis_market_factors(entity_type, entity_id))


@app.get("/gis/analysis/{entity_type}/{entity_id}/forecast", tags=["gis-analysis"])
def gis_forecast(entity_type: str, entity_id: str, years: int = 5) -> Any:
    return j(core.gis_forecast(entity_type, entity_id, years=years))


@app.get("/gis/analysis/{entity_type}/{entity_id}/scenarios", tags=["gis-analysis"])
def gis_scenarios(entity_type: str, entity_id: str, years: int = 5) -> Any:
    return j(core.gis_scenario_analysis(entity_type, entity_id, years=years))


@app.get("/gis/outlook/{entity_type}/{entity_id}", tags=["gis-analysis"], response_class=HTMLResponse)
def gis_outlook_report(
    entity_type: str,
    entity_id: str,
    years: int = 5,
    include_map: bool = True,
    include_news: bool = True,
    lang: str = Depends(ui_lang),
    theme: str = Depends(ui_theme),
) -> HTMLResponse:
    """Full investment-outlook report: cost/development, predictions, risks and a news ticker."""
    html = core.gis_outlook_report(entity_type, entity_id, years=years, include_map=include_map,
                                   include_news=include_news, lang=lang, theme=theme)
    return HTMLResponse(content=html)


# ------------------------------------------------------------------
# News ticker (real-estate market intelligence)
# ------------------------------------------------------------------


class NewsCreate(BaseModel):
    title: str
    source: str
    category: str = "market"
    sentiment: str = "neutral"
    impact_score: float = 0.0
    channel_type: str = "news"
    summary: Optional[str] = None
    url: Optional[str] = None
    city_id: Optional[str] = None
    scheme_id: Optional[str] = None
    tags: Optional[List[str]] = None


@app.get("/news", tags=["news"])
def news(
    category: Optional[str] = None,
    city: Optional[str] = None,
    scheme: Optional[str] = None,
    sentiment: Optional[str] = None,
    channel_type: Optional[str] = None,
    days: Optional[int] = None,
    limit: int = 50,
) -> Any:
    return j(core.news_list(category=category, city=city, scheme=scheme, sentiment=sentiment,
                            channel_type=channel_type, days=days, limit=limit))


@app.post("/news", tags=["news"], status_code=201)
def news_create(payload: NewsCreate) -> Any:
    result = j(core.news_add(**payload.model_dump(exclude_none=True)))
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/news/channels", tags=["news"])
def news_channels() -> Any:
    return j(core.news_channels())


@app.get("/news/impact", tags=["news"])
def news_impact(city: Optional[str] = None, scheme: Optional[str] = None, days: int = 120) -> Any:
    return j(core.news_impact(city=city, scheme=scheme, days=days))


@app.get("/news/ticker", tags=["news"])
def news_ticker(
    category: Optional[str] = None,
    city: Optional[str] = None,
    scheme: Optional[str] = None,
    limit: int = 25,
    speed_seconds: float = 70.0,
    lang: str = Depends(ui_lang),
) -> Any:
    """Scrolling ticker as an embeddable HTML fragment (text/html)."""
    html = core.news_ticker(category=category, city=city, scheme=scheme, limit=limit,
                            speed_seconds=speed_seconds, lang=lang)
    return Response(content=html, media_type="text/html")


@app.get("/news/ticker.html", tags=["news"], response_class=HTMLResponse)
def news_ticker_page(
    category: Optional[str] = None,
    city: Optional[str] = None,
    scheme: Optional[str] = None,
    limit: int = 25,
    speed_seconds: float = 70.0,
    lang: str = Depends(ui_lang),
    theme: str = Depends(ui_theme),
) -> HTMLResponse:
    """Standalone page hosting the ticker (handy for an iframe embed)."""
    fragment = core.news_ticker(category=category, city=city, scheme=scheme, limit=limit,
                                speed_seconds=speed_seconds, lang=lang)
    language = core.gis.get_language(lang)
    page = (
        f"<!DOCTYPE html><html lang=\"{language['code']}\" dir=\"{language['dir']}\"><head>"
        "<meta charset=\"utf-8\" />"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />"
        "<title>Real Estate News Ticker</title>"
        f"{core.gis.theme_style(theme)}"
        f"<style>body{{margin:0;background:var(--bg, #0f172a);font-family:{language['font_stack']}}}</style>"
        f"</head><body>{fragment}</body></html>"
    )
    return HTMLResponse(content=page)


# ------------------------------------------------------------------
# Dual-language + theme facilities
# ------------------------------------------------------------------


@app.get("/i18n/languages", tags=["ui"])
def i18n_languages() -> Any:
    """Languages available for maps, reports and the ticker (code, name, direction)."""
    return j(core.portal_languages())


@app.get("/i18n/strings/{lang}", tags=["ui"])
def i18n_strings(lang: str) -> Any:
    """Localisation dictionary for one language (English source -> translation)."""
    return j(core.portal_strings(lang))


@app.get("/ui/themes", tags=["ui"])
def ui_themes() -> Any:
    """Available UI themes and the CSS custom properties each one sets."""
    return j(core.portal_themes())


# ------------------------------------------------------------------
# Authentication (email / mobile + OTP-verified signup)
# ------------------------------------------------------------------


class SignupRequest(BaseModel):
    email: Optional[str] = None
    mobile: Optional[str] = None
    password: Optional[str] = None
    name: Optional[str] = None
    role: str = "user"
    sms_consent: bool = False


class OtpVerifyRequest(BaseModel):
    identifier: str
    code: str
    purpose: str = "signup"
    sms_consent: bool = False


class LoginRequest(BaseModel):
    identifier: str
    password: str
    sms_consent: bool = False


class IdentifierRequest(BaseModel):
    identifier: str
    sms_consent: bool = False


def _require_sms_consent(identifier: str, consent: bool) -> None:
    """Require and record explicit consent before sending an OTP by SMS."""
    if "@" not in (identifier or ""):
        if not consent:
            raise HTTPException(status_code=422, detail={
                "code": "sms_consent_required",
                "error": "Please consent to receive an SMS verification code.",
            })
        normalized = core.auth.normalize_identifier(identifier) or identifier
        core.auth.log_event("sms_otp_consent", normalized, detail="User consented to receive an SMS verification code")


class ResetPasswordRequest(BaseModel):
    identifier: str
    code: str
    new_password: str


class SetPasswordRequest(BaseModel):
    new_password: str
    current_password: Optional[str] = None


def _bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    token = authorization.strip()
    return token[7:].strip() if token.lower().startswith("bearer ") else token


def require_user(authorization: Optional[str] = Header(default=None, description="Bearer <token>")) -> Dict[str, Any]:
    """FastAPI guard: rejects the request unless a valid bearer token is supplied."""
    user = core.auth.current_user(_bearer_token(authorization))
    if user is None:
        raise HTTPException(
            status_code=401, detail="Missing or invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return core.auth.public_user(user)


def _auth_result(result: Any) -> Any:
    """Translate an auth error dict into an HTTP error (otherwise pass through)."""
    if isinstance(result, dict) and result.get("error"):
        status = {
            "invalid_credentials": 401,
            "unauthenticated": 401,
            "otp_required": 403,
            "suspended": 403,
            "no_otp": 404,
            "no_user": 404,
            "expired": 400,
            "invalid": 400,
            "invalid_email": 422,
            "invalid_mobile": 422,
            "identifier_required": 422,
            "weak_password": 422,
            "locked": 429,
            "rate_limited": 429,
            "cooldown": 429,
            "email_taken": 409,
            "mobile_taken": 409,
            "delivery_failed": 502,
        }.get(result.get("code"), 400)
        raise HTTPException(status_code=status, detail=result)
    return result


@app.post("/auth/signup", tags=["auth"], status_code=201)
def auth_signup(payload: SignupRequest) -> Any:
    """Register with an email and/or mobile number. The account stays *pending*
    until the OTP we send is verified with `/auth/verify-otp`."""
    if payload.mobile:
        _require_sms_consent(payload.mobile, payload.sms_consent)
    return _auth_result(j(core.auth_signup(**payload.model_dump(exclude_none=True, exclude={"sms_consent"}))))


@app.post("/auth/verify-otp", tags=["auth"])
def auth_verify_otp(payload: OtpVerifyRequest) -> Any:
    """Verify a signup/login/reset OTP. Activating a signup returns a bearer token."""
    return _auth_result(j(core.auth_verify_otp(payload.identifier, payload.code, purpose=payload.purpose)))


@app.post("/auth/resend-otp", tags=["auth"])
def auth_resend_otp(payload: OtpVerifyRequest) -> Any:
    """Re-send a verification code (cooldown + hourly cap apply)."""
    _require_sms_consent(payload.identifier, payload.sms_consent)
    return _auth_result(j(core.auth_resend_otp(payload.identifier, purpose=payload.purpose)))


@app.post("/auth/login", tags=["auth"])
def auth_login(payload: LoginRequest) -> Any:
    """Password login. Returns `401` for bad credentials and `403` for unverified accounts."""
    ident = core.auth.normalize_identifier(payload.identifier)
    user = core.auth.find_user(ident) if ident else None
    if user is not None and not user.verified and ident and "@" not in ident:
        _require_sms_consent(ident, payload.sms_consent)
    return _auth_result(j(core.auth_login(payload.identifier, payload.password)))


@app.post("/auth/otp/request", tags=["auth"])
def auth_request_otp(payload: IdentifierRequest) -> Any:
    """Start a passwordless login by sending an OTP."""
    _require_sms_consent(payload.identifier, payload.sms_consent)
    return _auth_result(j(core.auth_request_otp(payload.identifier)))


@app.post("/auth/otp/verify", tags=["auth"])
def auth_verify_login_otp(payload: OtpVerifyRequest) -> Any:
    """Complete a passwordless login with the OTP."""
    return _auth_result(j(core.auth_verify_login_otp(payload.identifier, payload.code)))


@app.post("/auth/password/reset-request", tags=["auth"])
def auth_request_password_reset(payload: IdentifierRequest) -> Any:
    """Send a password-reset code."""
    _require_sms_consent(payload.identifier, payload.sms_consent)
    return _auth_result(j(core.auth_request_password_reset(payload.identifier)))


@app.post("/auth/password/reset", tags=["auth"])
def auth_reset_password(payload: ResetPasswordRequest) -> Any:
    """Reset a password with the reset code (revokes all sessions)."""
    return _auth_result(j(core.auth_reset_password(payload.identifier, payload.code, payload.new_password)))


@app.post("/auth/password/set", tags=["auth"])
def auth_set_password(payload: SetPasswordRequest, authorization: Optional[str] = Header(default=None)) -> Any:
    """Set or change the password of the signed-in user (Bearer token required)."""
    return _auth_result(j(core.auth_set_password(_bearer_token(authorization) or "", payload.new_password,
                                                  payload.current_password)))


@app.get("/auth/me", tags=["auth"])
def auth_me(user: Dict[str, Any] = Depends(require_user)) -> Any:
    """Return the authenticated account (Bearer token required)."""
    return {"authenticated": True, "user": user}


@app.post("/auth/logout", tags=["auth"])
def auth_logout(user: Dict[str, Any] = Depends(require_user), authorization: Optional[str] = Header(default=None)) -> Any:
    """Revoke the bearer token."""
    return _auth_result(j(core.auth_logout(_bearer_token(authorization) or "")))


@app.post("/auth/refresh", tags=["auth"])
def auth_refresh(user: Dict[str, Any] = Depends(require_user), authorization: Optional[str] = Header(default=None)) -> Any:
    """Exchange a valid token for a fresh one."""
    return _auth_result(j(core.auth_refresh(_bearer_token(authorization) or "")))


@app.get("/auth/users", tags=["auth"])
def auth_users(role: Optional[str] = None, status: Optional[str] = None,
               user: Dict[str, Any] = Depends(require_user)) -> Any:
    """List accounts (Bearer token required)."""
    return _auth_result(j(core.auth_list_users(role=role, status=status)))


@app.get("/auth/otps", tags=["auth"])
def auth_otps(identifier: Optional[str] = None, purpose: Optional[str] = None, limit: int = 25) -> Any:
    """Dev view of outstanding verification codes (plaintext only when exposed)."""
    return j(core.auth_list_otps(identifier=identifier, purpose=purpose, limit=limit))


@app.get("/auth/notifications", tags=["auth"])
def auth_notifications(channel: Optional[str] = None, limit: int = 25) -> Any:
    """The simulated SMS/e-mail outbox."""
    return j(core.auth_notifications(channel=channel, limit=limit))


@app.get("/auth/events", tags=["auth"])
def auth_events(limit: int = 50) -> Any:
    """Authentication audit trail."""
    return j(core.auth_events(limit=limit))


@app.get("/auth/config", tags=["auth"])
def auth_config() -> Any:
    """OTP/session/password policy plus live counters."""
    return j(core.auth_config())


# ------------------------------------------------------------------
# My listings — listings owned by the signed-in account (portable app)
# ------------------------------------------------------------------


def _owned_property(property_id: str, user: Dict[str, Any]) -> Any:
    """Return the property if the caller owns it (admins may manage any)."""
    p = core.find_property(property_id)
    if p is None:
        raise HTTPException(status_code=404, detail=f"Property not found: {property_id}")
    is_admin = bool({"super_admin", "admin"} & set(user.get("roles") or []))
    if p.owner_user_id != user["id"] and not is_admin:
        raise HTTPException(status_code=403, detail="You can only manage your own listings")
    return p


@app.get("/me/listings", tags=["properties"])
def my_listings(status: Optional[str] = None, limit: int = 100,
                user: Dict[str, Any] = Depends(require_user)) -> Any:
    """Listings published by the signed-in account (Bearer token required)."""
    return j(core.list_owned_properties(user["id"], status=status, limit=limit))


@app.post("/me/listings", tags=["properties"], status_code=201)
def my_listing_create(payload: PropertyCreate, user: Dict[str, Any] = Depends(require_user)) -> Any:
    """Publish a listing owned by the signed-in account. Agents are attributed automatically."""
    data = payload.model_dump(exclude_none=True)
    data["owner_user_id"] = user["id"]
    if user.get("agent_id") and not data.get("agent_id"):
        data["agent_id"] = user["agent_id"]
    result = j(core.add_property(**data))
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.put("/me/listings/{property_id}", tags=["properties"])
def my_listing_update(property_id: str, payload: PropertyUpdate,
                      user: Dict[str, Any] = Depends(require_user)) -> Any:
    """Edit one of your listings, e.g. ``{"status": "sold"}``."""
    _owned_property(property_id, user)
    return j(core.update_property(property_id, **payload.model_dump(exclude_none=True)))


@app.delete("/me/listings/{property_id}", tags=["properties"])
def my_listing_delete(property_id: str, user: Dict[str, Any] = Depends(require_user)) -> Any:
    """Remove one of your listings."""
    _owned_property(property_id, user)
    return j(core.delete_property(property_id))


UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "media", "uploads")
UPLOAD_MAX_BYTES = 5 * 1024 * 1024
_IMAGE_SIGNATURES = {b"\xff\xd8\xff": "jpg", b"\x89PNG": "png", b"RIFF": "webp"}


class PhotoUpload(BaseModel):
    data_url: str  # "data:image/jpeg;base64,..." or bare base64
    is_primary: bool = False


@app.post("/me/listings/{property_id}/photos", tags=["properties"], status_code=201)
def my_listing_add_photo(property_id: str, payload: PhotoUpload,
                         user: Dict[str, Any] = Depends(require_user)) -> Any:
    """Attach a photo (JPEG/PNG/WebP, max 5 MB, base64) to one of your listings."""
    p = _owned_property(property_id, user)
    url = _save_upload(payload.data_url)
    if payload.is_primary:
        p.image_urls.insert(0, url)
    else:
        p.image_urls.append(url)
    core.image_store("property", p.id, url, is_primary=payload.is_primary)
    return {"property_id": p.id, "url": url, "image_urls": p.image_urls}


def _save_upload(data_url: str) -> str:
    """Store a base64 photo (JPEG / PNG / WebP, 5 MB at most) under media/uploads; returns its URL."""
    encoded = data_url.split(",")[-1]
    if len(encoded) > UPLOAD_MAX_BYTES * 4 // 3 + 4:
        raise HTTPException(status_code=413, detail="Photo must be between 1 byte and 5 MB")
    try:
        raw = base64.b64decode(encoded, validate=False)
    except Exception:
        raise HTTPException(status_code=400, detail="data_url is not valid base64")
    if not raw or len(raw) > UPLOAD_MAX_BYTES:
        raise HTTPException(status_code=413, detail="Photo must be between 1 byte and 5 MB")
    ext = next((e for sig, e in _IMAGE_SIGNATURES.items() if raw.startswith(sig)), None)
    if ext is None or (ext == "webp" and raw[8:12] != b"WEBP"):
        raise HTTPException(status_code=415, detail="Only JPEG, PNG or WebP photos are accepted")
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    name = f"{core.uuid.uuid4().hex}.{ext}"
    with open(os.path.join(UPLOAD_DIR, name), "wb") as fh:
        fh.write(raw)
    return f"/media/uploads/{name}"


@app.post("/bigprojects/{project_id}/photos", tags=["big-projects"], status_code=201)
def big_project_add_photo(project_id: str, payload: PhotoUpload) -> Any:
    """Attach a photo taken on site (base64 JPEG / PNG / WebP) to a big project."""
    b = core.find_project(project_id)
    if not b:
        raise HTTPException(status_code=404, detail="Big project not found")
    url = _save_upload(payload.data_url)
    if payload.is_primary:
        b.image_urls.insert(0, url)
    else:
        b.image_urls.append(url)
    b.image_library = [*(b.image_library or []), url]
    b.updated_at = datetime.now()
    return {"project_id": b.id, "url": url, "image_urls": b.image_urls}


@app.post("/geo/megaprojects/{project_id}/photos", tags=["places"], status_code=201)
def geo_megaproject_add_photo(project_id: str, payload: PhotoUpload) -> Any:
    """Attach a photo taken on site to an infrastructure mega project (GIS managers)."""
    try:
        return megaprojects.admin_add_photo(project_id, _save_upload(payload.data_url), payload.is_primary)
    except KeyError:
        raise HTTPException(status_code=404, detail="Project not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/admin/locations", tags=["admin"])
def admin_locations(kind: str = "property", q: str = "", status: str = "problems", page: int = 1, page_size: int = 30) -> Any:
    """Listings, big projects or mega-project points with a missing or doubtful location (Locate tool)."""
    try:
        return locations.search(kind=kind, q=q, status=status, page=page, page_size=page_size)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/geo/nearby-entities", tags=["places"])
def geo_nearby_entities(lat: float, lon: float, radius_m: float = 300.0, limit: int = 20) -> Any:
    """Listings, big projects and mega projects around a point — for surveying on site."""
    r_km = max(0.02, min(radius_m, 5000.0)) / 1000.0
    cities = {c.id: c.name for c in core.cities_db}

    def near(la: Optional[float], lo: Optional[float]) -> Optional[float]:
        return None if la is None or lo is None else core.haversine_km(lat, lon, la, lo)

    # a project's unit listings follow the project, so the project stands for them here
    props = sorted(((d, p) for p in core.properties_db if p.status == "active" and not p.project_id
                    and (d := near(p.latitude, p.longitude)) is not None and d <= r_km),
                   key=lambda x: x[0])[:limit]
    projects = sorted(((d, b) for b in core.big_projects_db if (d := near(b.latitude, b.longitude)) is not None and d <= r_km),
                      key=lambda x: x[0])[:limit]
    megas = sorted(((megaprojects.distance_km(m, lat, lon), m) for m in megaprojects.all_projects() if not m.get("portal_project")),
                   key=lambda x: x[0])
    return {
        "at": {"latitude": lat, "longitude": lon, "radius_m": round(r_km * 1000)},
        "properties": [{"id": p.id, "title": p.title, "price": p.price, "category": p.category, "city": cities.get(p.city_id),
                        "owner_user_id": p.owner_user_id, "project_id": p.project_id, "image": (p.image_urls or [None])[0],
                        "latitude": p.latitude, "longitude": p.longitude, "distance_m": round(d * 1000)} for d, p in props],
        "projects": [{"id": b.id, "name": b.name, "project_type": b.project_type, "status": b.status, "city": cities.get(b.city_id),
                      "image": (b.image_urls or [None])[0], "latitude": b.latitude, "longitude": b.longitude,
                      "distance_m": round(d * 1000)} for d, b in projects],
        "megaprojects": [{"id": m["id"], "name": m["name"], "type": m["type"], "status": m["status"], "city": m.get("city"),
                          "geometry_type": m["geometry"]["type"], "image": m.get("image"), "distance_m": round(d * 1000)}
                         for d, m in megas if d <= r_km][:limit],
    }


@app.get("/media/uploads/{name}", tags=["properties"], include_in_schema=False)
def uploaded_media(name: str) -> Any:
    """Serve a photo uploaded through ``/me/listings/{id}/photos``."""
    if not re.fullmatch(r"[0-9a-f]{32}\.(jpg|png|webp)", name):
        raise HTTPException(status_code=404, detail="Not found")
    path = os.path.join(UPLOAD_DIR, name)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path, headers={"Cache-Control": "public, max-age=31536000, immutable"})


# ------------------------------------------------------------------
# Hierarchy: create/read parity for every hierarchy MCP tool
# ------------------------------------------------------------------


class CityCreate(BaseModel):
    name: str
    state: Optional[str] = None
    country: str = "Pakistan"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    description: Optional[str] = None


@app.post("/cities", tags=["hierarchy"], status_code=201)
def add_city(payload: CityCreate) -> Any:
    """Add a city."""
    return j(core.add_city(**payload.model_dump(exclude_none=True)))


@app.get("/cities/{city}", tags=["hierarchy"])
def get_city_details(city: str) -> Any:
    """Full details for a city (by id or name): schemes, properties and value."""
    return j(core.get_city_details(city))


@app.get("/cities/{city}/coordinates", tags=["hierarchy"])
def get_city_coordinates(city: str) -> Any:
    """Latitude/longitude of a city (by id or name)."""
    return j(core.get_city_coordinates(city))


@app.post("/schemes", tags=["hierarchy"], status_code=201)
def add_housing_scheme(payload: Dict[str, Any]) -> Any:
    """Add a housing scheme / society."""
    return j(core.add_housing_scheme(**payload))


@app.put("/schemes/{scheme_id}", tags=["hierarchy"])
def update_housing_scheme(scheme_id: str, payload: Dict[str, Any]) -> Any:
    """Update a housing scheme — e.g. development_status, approval_authority, possession_status,
    utilities, population, developer."""
    try:
        result = j(core.update_housing_scheme(scheme_id, **payload))
    except TypeError as exc:  # an unknown field
        raise HTTPException(status_code=422, detail=str(exc))
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/blocks", tags=["hierarchy"])
def list_blocks(scheme: Optional[str] = None) -> Any:
    """List blocks / zones / areas, optionally filtered by scheme."""
    return j(core.list_blocks(scheme=scheme))


@app.post("/blocks", tags=["hierarchy"], status_code=201)
def add_block_zone_area(payload: Dict[str, Any]) -> Any:
    """Add a block / zone / area to a scheme."""
    return j(core.add_block_zone_area(**payload))


class CoordinatesUpdate(BaseModel):
    latitude: float
    longitude: float


@app.put("/properties/{property_id}/coordinates", tags=["properties"])
def set_property_coordinates(property_id: str, payload: CoordinatesUpdate) -> Any:
    """Set (or correct) the coordinates of a property."""
    return j(core.set_property_coordinates(property_id, payload.latitude, payload.longitude))


@app.get("/distance", tags=["gis"])
def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> Any:
    """Great-circle distance between two points (km)."""
    return j(core.calculate_distance(lat1, lon1, lat2, lon2))


# ------------------------------------------------------------------
# Big projects: create/update/delete + media parity
# ------------------------------------------------------------------


@app.post("/bigprojects", tags=["big-projects"], status_code=201)
def add_big_project(payload: Dict[str, Any]) -> Any:
    """Add a big project (mall / tower / mixed-use / compound / plaza / office complex)."""
    return j(core.add_big_project(**payload))


@app.put("/bigprojects/{project_id}", tags=["big-projects"])
def update_big_project(project_id: str, payload: Dict[str, Any]) -> Any:
    """Update a big project."""
    return j(core.update_big_project(project_id, **payload))


@app.delete("/bigprojects/{project_id}", tags=["big-projects"])
def delete_big_project(project_id: str) -> Any:
    """Delete a big project."""
    return j(core.delete_big_project(project_id))


@app.post("/bigprojects/{project_id}/amenities", tags=["big-projects"], status_code=201)
def add_project_amenity(project_id: str, payload: Dict[str, Any]) -> Any:
    """Add an amenity to a big project (``{"amenity": "..."}``)."""
    return j(core.add_project_amenity(project_id, payload.get("amenity", "")))


@app.post("/bigprojects/{project_id}/floor-plans", tags=["big-projects"], status_code=201)
def add_project_floor_plan(project_id: str, payload: Dict[str, Any]) -> Any:
    """Attach a floor plan (``{"floor_plan_url": "..."}``)."""
    return j(core.add_project_floor_plan(project_id, payload.get("floor_plan_url", "")))


@app.post("/bigprojects/{project_id}/maps", tags=["big-projects"], status_code=201)
def add_project_map(project_id: str, payload: Dict[str, Any]) -> Any:
    """Attach a map image (``{"map_url": "..."}``)."""
    return j(core.add_project_map(project_id, payload.get("map_url", "")))


@app.post("/bigprojects/{project_id}/multimedia", tags=["big-projects"], status_code=201)
def add_project_multimedia(project_id: str, payload: Dict[str, Any]) -> Any:
    """Attach multimedia (``{"media_type": "video", "url": "..."}``)."""
    return j(core.add_project_multimedia(project_id, payload.get("media_type", "video"), payload.get("url", "")))


# ------------------------------------------------------------------
# Images
# ------------------------------------------------------------------


@app.get("/images/{entity_type}/{entity_id}", tags=["images"])
def image_list(entity_type: str, entity_id: str) -> Any:
    """List images stored for an entity."""
    return j(core.image_list(entity_type, entity_id))


@app.post("/images", tags=["images"], status_code=201)
def image_store(payload: Dict[str, Any]) -> Any:
    """Store an image URL against an entity."""
    return j(core.image_store(**payload))


@app.post("/images/{entity_type}/{entity_id}/primary", tags=["images"])
def image_set_primary(entity_type: str, entity_id: str, payload: Dict[str, Any]) -> Any:
    """Mark one stored image as the primary/cover image (``{"image_index": 0}``)."""
    return j(core.image_set_primary(entity_type, entity_id, int(payload.get("image_index", 0))))


@app.delete("/images/{entity_type}/{entity_id}/{image_index}", tags=["images"])
def image_delete(entity_type: str, entity_id: str, image_index: int) -> Any:
    """Delete a stored image by index."""
    return j(core.image_delete(entity_type, entity_id, image_index))


# ------------------------------------------------------------------
# Memory
# ------------------------------------------------------------------


@app.get("/memory/retrieve", tags=["memory"])
def memory_retrieve(key: str) -> Any:
    """Read a value from long-term memory or the near cache."""
    return j(core.memory_retrieve(key))


@app.delete("/memory", tags=["memory"])
def memory_clear() -> Any:
    """Clear the near cache and long-term memory."""
    return j(core.memory_clear())


# ------------------------------------------------------------------
# GIS: boundaries, zones, destination, point-in-layer
# ------------------------------------------------------------------


@app.post("/gis/boundaries", tags=["gis"], status_code=201)
def gis_add_boundary(payload: Dict[str, Any]) -> Any:
    """Add a boundary polygon layer (scheme/society outline)."""
    return j(core.gis_add_boundary(**payload))


@app.post("/gis/zones", tags=["gis"], status_code=201)
def gis_add_zone(payload: Dict[str, Any]) -> Any:
    """Add a zone layer (residential / commercial / amenity)."""
    return j(core.gis_add_zone(**payload))


@app.get("/gis/destination", tags=["gis"])
def gis_destination(latitude: float, longitude: float, bearing: float, distance_m: float) -> Any:
    """Project a point a given bearing/distance (destination point)."""
    return j(core.gis_destination(latitude, longitude, bearing, distance_m))


@app.get("/gis/point-in-layer", tags=["gis"])
def gis_point_in_layer(layer_id: str, latitude: float, longitude: float) -> Any:
    """Test whether a point falls inside a layer's polygons."""
    return j(core.gis_point_in_layer(layer_id, latitude, longitude))


# ------------------------------------------------------------------
# CRM parity (agents, customers, lead ops, interactions, appointments)
# ------------------------------------------------------------------


@app.post("/crm/agents", tags=["crm"], status_code=201)
def crm_add_agent(payload: Dict[str, Any]) -> Any:
    """Add a sales agent."""
    return j(core.crm_add_agent(**payload))


# ============================================================ CRM: insights, AI, channels, webhooks


class CrmSendRequest(BaseModel):
    channel: str  # whatsapp | email | sms
    body: str = Field(..., min_length=1, max_length=4000)
    subject: Optional[str] = None
    to: Optional[str] = None  # defaults to the lead's / customer's phone or e-mail
    entity_type: Optional[str] = "lead"
    entity_id: Optional[str] = None
    agent_id: Optional[str] = None


class CrmDraftRequest(BaseModel):
    entity_type: str = "lead"
    entity_id: str
    channel: str = "whatsapp"
    goal: str = "follow_up"
    lang: str = "en"
    tone: str = "friendly"
    notes: Optional[str] = None


class CrmNoteRequest(BaseModel):
    audio_base64: Optional[str] = None
    mime_type: str = "audio/webm"
    text: Optional[str] = None
    entity_type: Optional[str] = "lead"
    entity_id: Optional[str] = None
    agent_id: Optional[str] = None
    apply: bool = True


class CrmAskRequest(BaseModel):
    question: Optional[str] = None
    audio_base64: Optional[str] = None
    mime_type: str = "audio/webm"
    lang: str = "en"
    speak: bool = False


async def _transcribe_b64(b64: str, mime: str, request: Request) -> str:
    if not openai_voice.configured():
        raise HTTPException(status_code=501, detail="Voice needs OPENAI_API_KEY in backend/.env — type the note instead")
    if len(b64) > MAX_AUDIO_B64:
        raise HTTPException(status_code=413, detail="Recording too long (25 MB max)")
    ai_guard.check(request, "voice")
    try:
        audio = base64.b64decode(b64.split(",")[-1], validate=False)
    except Exception:
        raise HTTPException(status_code=400, detail="audio_base64 is not valid base64")
    if not audio:
        raise HTTPException(status_code=400, detail="Empty audio")
    try:
        return await asyncio.to_thread(openai_voice.transcribe, audio, mime)
    except openai_voice.VoiceError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))


@app.get("/crm/insights", tags=["crm"])
def crm_insights(days: int = 30, agent_id: Optional[str] = None) -> Any:
    """Everything the CRM dashboard shows: KPIs (leads, conversion, first-response time, pipeline,
    won value, tasks, appointments), daily trend, sources, statuses, cities, channel mix, funnel,
    pipeline by stage, agent leaderboard, priority leads with next best action, at-risk deals,
    today's agenda and which messaging channels are live. ``agent_id`` limits it to one agent's book."""
    return crm_ai.insights(max(7, min(days, 365)), access.agent_scope() or agent_id)


@app.get("/crm/channels", tags=["crm"])
def crm_channels_status() -> Any:
    """Which outbound channels really send (e-mail / SMS / WhatsApp) and the inbound webhooks."""
    return {**crm_channels.status(), "ai": crm_ai.ai_available(), "voice": openai_voice.configured()}


@app.post("/crm/messages/send", tags=["crm"])
def crm_send_message(payload: CrmSendRequest) -> Any:
    """Send a WhatsApp, e-mail or SMS to a lead / customer and log it on their timeline. Channels
    that are not configured are simulated (logged, not delivered) — see GET /crm/channels."""
    entity = None
    if payload.entity_id:
        entity, err = crm_ai._entity(payload.entity_type or "lead", payload.entity_id)
        if err:
            raise HTTPException(status_code=404, detail=err)
    to = payload.to or (getattr(entity, "email", None) if payload.channel == "email" else getattr(entity, "phone", None))
    if not to:
        raise HTTPException(status_code=422, detail=f"No {'e-mail address' if payload.channel == 'email' else 'phone number'} for this contact")
    res = crm_channels.send(payload.channel, to, payload.body, payload.subject)
    interaction = None
    if entity is not None and res["status"] in ("sent", "simulated"):
        summary = (f"{payload.subject}: " if payload.subject else "") + payload.body
        if res["status"] == "simulated":
            summary += " (simulated — channel not configured)"
        interaction = j(core.crm_log_interaction(entity_type=payload.entity_type or "lead", entity_id=entity.id, summary=summary[:1000],
                                                 channel=payload.channel, direction="outbound",
                                                 agent_id=payload.agent_id or getattr(entity, "assigned_agent_id", None)))
        if getattr(entity, "status", None) == "new":
            entity.status = "contacted"
            entity.updated_at = crm_ai.datetime.now()
    if res["status"] == "failed":
        raise HTTPException(status_code=502, detail=res["error"] or "Sending failed")
    return {**res, "interaction": interaction}


@app.post("/crm/ai/lead-brief/{lead_id}", tags=["crm"])
async def crm_ai_lead_brief(lead_id: str, request: Request, lang: str = "en") -> Any:
    """AI lead brief: summary, temperature, next best action with channel and urgency, follow-up
    date, talking points, risks, and ready-to-send WhatsApp / SMS / e-mail drafts (en or ur)."""
    if crm_ai.ai_available():
        ai_guard.check(request, "chat")
    out = await asyncio.to_thread(crm_ai.lead_brief, lead_id, lang)
    if "error" in out:
        raise HTTPException(status_code=404, detail=out["error"])
    return out


@app.post("/crm/ai/draft", tags=["crm"])
async def crm_ai_draft(payload: CrmDraftRequest, request: Request) -> Any:
    """Draft one message for a lead / customer: goal follow_up | new_matches | site_visit |
    price_update | re_engage | thank_you | proposal, any tone, English or Urdu."""
    if crm_ai.ai_available():
        ai_guard.check(request, "chat")
    out = await asyncio.to_thread(crm_ai.draft_message, payload.entity_type, payload.entity_id, payload.channel,
                                  payload.goal, payload.lang, payload.tone, payload.notes)
    if "error" in out:
        raise HTTPException(status_code=404, detail=out["error"])
    return out


@app.post("/crm/ai/note", tags=["crm"])
async def crm_ai_note(payload: CrmNoteRequest, request: Request) -> Any:
    """A voice note (``audio_base64``) or typed note about a client: transcribed, summarised and
    turned into CRM data (sentiment, budget, next step, follow-up date, suggested status, tasks).
    With ``apply`` and an entity it is logged on the timeline and its tasks are created."""
    text = (payload.text or "").strip()
    if payload.audio_base64:
        text = (await _transcribe_b64(payload.audio_base64, payload.mime_type, request)).strip()
    if not text:
        raise HTTPException(status_code=422, detail="Record or type a note")
    if crm_ai.ai_available():
        ai_guard.check(request, "chat")
    analysis = await asyncio.to_thread(crm_ai.analyse_note, text, payload.entity_type, payload.entity_id)
    applied = None
    if payload.apply and payload.entity_id:
        applied = crm_ai.apply_note(analysis, text, payload.entity_type or "lead", payload.entity_id, payload.agent_id,
                                    channel="voice_note" if payload.audio_base64 else "note")
        if "error" in applied:
            raise HTTPException(status_code=404, detail=applied["error"])
    return {"transcript": text, "analysis": analysis, "applied": applied}


@app.post("/crm/ai/ask", tags=["crm"])
async def crm_ai_ask(payload: CrmAskRequest, request: Request) -> Any:
    """CRM copilot: ask in text or by voice ("who should I call first?", "deals at risk?",
    "leads in Lahore") and get an answer from live CRM data — spoken back with ``speak``."""
    question = (payload.question or "").strip()
    transcript = None
    if payload.audio_base64:
        transcript = question = (await _transcribe_b64(payload.audio_base64, payload.mime_type, request)).strip()
    if not question:
        raise HTTPException(status_code=422, detail="Ask a question")
    if crm_ai.ai_available():
        ai_guard.check(request, "chat")
    out = await asyncio.to_thread(crm_ai.ask, question, payload.lang, access.agent_scope())
    out["question"] = question
    out["transcript"] = transcript
    if payload.speak and openai_voice.configured():
        try:
            spoken = openai_voice.clean_for_speech(out["answer"])[:MAX_SPEAK_CHARS]
            audio, mime = await asyncio.to_thread(openai_voice.speak, spoken, "ur" if payload.lang == "ur" else None)
            out["audio_base64"], out["mime_type"] = base64.b64encode(audio).decode(), mime
        except openai_voice.VoiceError:
            pass
    return out


@app.post("/crm/webhooks/lead", tags=["crm"])
def crm_webhook_lead(payload: Dict[str, Any], source: str = "website",
                     x_webhook_secret: Optional[str] = Header(default=None)) -> Any:
    """Inbound leads from website forms, Facebook / Instagram lead ads (via Zapier / Make; Meta
    ``field_data`` is understood), property portals or any tool that can POST JSON. Recognises
    name / full_name, phone / phone_number / mobile, email, message, city, budget, property_id.
    De-duplicates by phone or e-mail and routes new leads to an agent. When
    ``PORTAL_CRM_WEBHOOK_SECRET`` is set, send it in the ``X-Webhook-Secret`` header."""
    secret = os.getenv("PORTAL_CRM_WEBHOOK_SECRET", "").strip()
    if secret and not hmac.compare_digest((x_webhook_secret or "").encode(), secret.encode()):
        raise HTTPException(status_code=401, detail="Bad webhook secret")
    return crm_ai.ingest_lead(payload, source)


@app.get("/crm/webhooks/whatsapp", tags=["crm"])
def crm_webhook_whatsapp_verify(request: Request) -> Any:
    """Meta webhook verification (``hub.verify_token`` must equal ``PORTAL_WHATSAPP_VERIFY_TOKEN``)."""
    q = request.query_params
    token = os.getenv("PORTAL_WHATSAPP_VERIFY_TOKEN", "").strip()
    if q.get("hub.mode") == "subscribe" and token and q.get("hub.verify_token") == token:
        return PlainTextResponse(q.get("hub.challenge", ""))
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/crm/webhooks/whatsapp", tags=["crm"])
async def crm_webhook_whatsapp(request: Request) -> Any:
    """Incoming WhatsApp messages (Meta Cloud API webhook) land on the sender's lead timeline; a
    new number becomes a new lead routed to an agent. When ``PORTAL_WHATSAPP_APP_SECRET`` (the Meta
    app secret) is set, the ``X-Hub-Signature-256`` signature must match."""
    raw = await request.body()
    app_secret = os.getenv("PORTAL_WHATSAPP_APP_SECRET", "").strip()
    if app_secret:
        sent = request.headers.get("x-hub-signature-256", "")
        expected = "sha256=" + hmac.new(app_secret.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sent.encode(), expected.encode()):
            raise HTTPException(status_code=401, detail="Bad signature")
    try:
        payload = json.loads(raw or b"{}")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    return crm_ai.whatsapp_inbound(payload if isinstance(payload, dict) else {})


@app.get("/crm/agents/{agent_id}", tags=["crm"])
def crm_get_agent(agent_id: str) -> Any:
    """Fetch one agent with their pipeline."""
    return j(core.crm_get_agent(agent_id))


@app.put("/crm/agents/{agent_id}", tags=["crm"])
def crm_update_agent(agent_id: str, payload: Dict[str, Any]) -> Any:
    """Update an agent."""
    return j(core.crm_update_agent(agent_id, **payload))


@app.post("/crm/customers", tags=["crm"], status_code=201)
def crm_add_customer(payload: Dict[str, Any]) -> Any:
    """Add a customer."""
    return j(core.crm_add_customer(**payload))


@app.get("/crm/customers/{customer_id}", tags=["crm"])
def crm_get_customer(customer_id: str) -> Any:
    """Fetch one customer with their deals and interactions."""
    return j(core.crm_get_customer(customer_id))


@app.put("/crm/leads/{lead_id}", tags=["crm"])
def crm_update_lead(lead_id: str, payload: Dict[str, Any]) -> Any:
    """Update a lead (status, score, budget, assignment)."""
    return j(core.crm_update_lead(lead_id, **payload))


@app.post("/crm/leads/{lead_id}/assign", tags=["crm"])
def crm_assign_lead(lead_id: str, payload: Dict[str, Any]) -> Any:
    """Assign a lead to an agent (``{"agent_id": "..."}``)."""
    return j(core.crm_assign_lead(lead_id, payload.get("agent_id", "")))


@app.get("/crm/interactions", tags=["crm"])
def crm_list_interactions(entity_id: Optional[str] = None, limit: int = 200) -> Any:
    """List interactions for an entity, or the latest across the CRM (newest first). Agents see
    the timeline of their own leads and customers."""
    mine = access.agent_scope()
    data = j(core.crm_list_interactions(entity_id=entity_id, limit=limit if not mine else 2000))
    if mine:
        own = {x.id for x in core.leads_db if x.assigned_agent_id == mine} | {c.id for c in core.customers_db if c.assigned_agent_id == mine}
        data["interactions"] = [i for i in data["interactions"] if i.get("entity_id") in own or i.get("agent_id") == mine][:limit]
        data["count"] = len(data["interactions"])
    return data


@app.post("/crm/interactions", tags=["crm"], status_code=201)
def crm_log_interaction(payload: Dict[str, Any]) -> Any:
    """Log an interaction against a lead / customer / deal."""
    return j(core.crm_log_interaction(**payload))


@app.put("/crm/deals/{deal_id}/stage", tags=["crm"])
def crm_update_deal_stage(deal_id: str, payload: Dict[str, Any]) -> Any:
    """Move a deal to a new stage (and/or probability)."""
    return j(core.crm_update_deal_stage(deal_id, **payload))


@app.put("/crm/tasks/{task_id}/complete", tags=["crm"])
def crm_complete_task(task_id: str, payload: Optional[Dict[str, Any]] = None) -> Any:
    """Complete (or otherwise update the status of) a task."""
    status = (payload or {}).get("status", "done")
    return j(core.crm_complete_task(task_id, status=status))


@app.post("/crm/appointments", tags=["crm"], status_code=201)
def crm_schedule_appointment(payload: Dict[str, Any]) -> Any:
    """Schedule an appointment."""
    return j(core.crm_schedule_appointment(**payload))


# ==================================================================
# ACCOUNTING & FINANCE
# ==================================================================


class AccountCreateRequest(BaseModel):
    code: str
    name: str
    account_type: str = "asset"
    subtype: Optional[str] = None
    parent_code: Optional[str] = None
    normal_side: Optional[str] = None
    description: Optional[str] = None
    opening_balance: float = 0.0


class AccountUpdateRequest(BaseModel):
    name: Optional[str] = None
    subtype: Optional[str] = None
    description: Optional[str] = None
    active: Optional[bool] = None


class JournalPostRequest(BaseModel):
    lines: List[Dict[str, Any]]
    date: Optional[str] = None
    memo: Optional[str] = None
    reference: Optional[str] = None
    created_by: Optional[str] = None


class InvoiceCreateRequest(BaseModel):
    counterparty: str
    lines: List[Dict[str, Any]]
    invoice_type: str = "receivable"
    issue_date: Optional[str] = None
    due_date: Optional[str] = None
    tax_rate: Optional[float] = None
    property_id: Optional[str] = None
    scheme_id: Optional[str] = None
    city_id: Optional[str] = None
    lease_id: Optional[str] = None
    notes: Optional[str] = None
    auto_post: bool = False


class PaymentRequest(BaseModel):
    amount: float
    invoice_id: Optional[str] = None
    direction: str = "in"
    method: str = "bank_transfer"
    account_code: str = "1010"
    date: Optional[str] = None
    counterparty: Optional[str] = None
    reference: Optional[str] = None
    notes: Optional[str] = None


class ExpenseRequest(BaseModel):
    amount: float
    account_code: str = "5900"
    category: str = "misc"
    date: Optional[str] = None
    vendor: Optional[str] = None
    description: Optional[str] = None
    tax_amount: float = 0.0
    paid: bool = True
    property_id: Optional[str] = None
    scheme_id: Optional[str] = None
    city_id: Optional[str] = None


class LeaseRequest(BaseModel):
    tenant: str
    rent_amount: float
    property_id: Optional[str] = None
    unit_label: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    billing_cycle: str = "monthly"
    escalation_rate: Optional[float] = None
    security_deposit: float = 0.0
    tenant_id: Optional[str] = None
    city_id: Optional[str] = None
    scheme_id: Optional[str] = None
    notes: Optional[str] = None


class BudgetRequest(BaseModel):
    name: str
    lines: Dict[str, float]
    fiscal_year: str = ""
    scope: str = "portfolio"
    scope_id: Optional[str] = None
    notes: Optional[str] = None


class RentInvoiceRequest(BaseModel):
    period_month: Optional[int] = None
    year: Optional[int] = None
    auto_post: bool = True


@app.get("/accounting/info", tags=["accounting"])
def accounting_info() -> Any:
    """Accounting configuration, allowed values and record counts."""
    return j(core.accounting_info())


@app.get("/accounting/accounts", tags=["accounting"])
def accounting_accounts(account_type: Optional[str] = None, subtype: Optional[str] = None,
                        active_only: bool = False) -> Any:
    """Chart of accounts with live balances."""
    return j(core.accounting_chart_of_accounts(account_type=account_type, subtype=subtype,
                                               active_only=active_only))


@app.post("/accounting/accounts", tags=["accounting"], status_code=201)
def accounting_create_account(payload: AccountCreateRequest) -> Any:
    """Add a ledger account."""
    return j(core.accounting_create_account(**payload.model_dump(exclude_none=True)))


@app.put("/accounting/accounts/{code}", tags=["accounting"])
def accounting_update_account(code: str, payload: AccountUpdateRequest) -> Any:
    """Rename / reclassify / deactivate an account."""
    return j(core.accounting_update_account(code, **payload.model_dump(exclude_none=True)))


@app.get("/accounting/accounts/{code}/balance", tags=["accounting"])
def accounting_account_balance(code: str, as_of: Optional[str] = None) -> Any:
    """Debit/credit movement and signed balance of one account."""
    return j(core.accounting_account_balance(code, as_of))


@app.get("/accounting/chart", tags=["accounting"])
def accounting_chart() -> Any:
    """Full chart of accounts with balances (all types)."""
    return j(core.accounting_chart_of_accounts())


@app.post("/accounting/journal", tags=["accounting"], status_code=201)
def accounting_journal_post(payload: JournalPostRequest) -> Any:
    """Post a balanced double-entry journal entry."""
    return j(core.accounting_journal_post(**payload.model_dump(exclude_none=True)))


@app.get("/accounting/journal", tags=["accounting"])
def accounting_journal_list(from_date: Optional[str] = None, to_date: Optional[str] = None,
                            source: Optional[str] = None, account: Optional[str] = None,
                            property_id: Optional[str] = None, limit: int = 50) -> Any:
    """List journal entries."""
    return j(core.accounting_journal_list(from_date=from_date, to_date=to_date, source=source,
                                          account=account, property_id=property_id, limit=limit))


@app.get("/accounting/journal/{entry_id}", tags=["accounting"])
def accounting_journal_get(entry_id: str) -> Any:
    """Fetch one journal entry."""
    return j(core.accounting_journal_get(entry_id))


@app.post("/accounting/journal/{entry_id}/void", tags=["accounting"])
def accounting_journal_void(entry_id: str, payload: Optional[Dict[str, Any]] = None) -> Any:
    """Void a journal entry (``{"reason": "..."}`` optional)."""
    return j(core.accounting_journal_void(entry_id, (payload or {}).get("reason")))


@app.get("/accounting/trial-balance", tags=["accounting"])
def accounting_trial_balance(as_of: Optional[str] = None) -> Any:
    """Trial balance at a date."""
    return j(core.accounting_trial_balance(as_of))


@app.get("/accounting/ledger/{account_code}", tags=["accounting"])
def accounting_general_ledger(account_code: str, from_date: Optional[str] = None,
                              to_date: Optional[str] = None) -> Any:
    """General ledger (running balance) for one account."""
    return j(core.accounting_general_ledger(account_code, from_date, to_date))


@app.get("/accounting/profit-and-loss", tags=["accounting"])
def accounting_profit_and_loss(from_date: Optional[str] = None, to_date: Optional[str] = None,
                               property_id: Optional[str] = None, scheme_id: Optional[str] = None,
                               city_id: Optional[str] = None) -> Any:
    """Profit & loss, optionally scoped to a property / scheme / city."""
    return j(core.accounting_profit_and_loss(from_date, to_date, property_id=property_id,
                                             scheme_id=scheme_id, city_id=city_id))


@app.get("/accounting/balance-sheet", tags=["accounting"])
def accounting_balance_sheet(as_of: Optional[str] = None) -> Any:
    """Balance sheet at a date."""
    return j(core.accounting_balance_sheet(as_of))


@app.get("/accounting/cash-flow", tags=["accounting"])
def accounting_cash_flow(from_date: Optional[str] = None, to_date: Optional[str] = None) -> Any:
    """Cash-flow statement (operating / investing / financing)."""
    return j(core.accounting_cash_flow(from_date, to_date))


@app.get("/accounting/ratios", tags=["accounting"])
def accounting_ratios(as_of: Optional[str] = None) -> Any:
    """Liquidity, leverage and profitability ratios."""
    return j(core.accounting_ratios(as_of))


@app.get("/accounting/dashboard", tags=["accounting"])
def accounting_dashboard(as_of: Optional[str] = None) -> Any:
    """Finance dashboard snapshot."""
    return j(core.accounting_dashboard(as_of))


@app.post("/accounting/invoices", tags=["accounting"], status_code=201)
def accounting_invoice_create(payload: InvoiceCreateRequest) -> Any:
    """Create a receivable or payable invoice."""
    return j(core.accounting_invoice_create(**payload.model_dump(exclude_none=True)))


@app.get("/accounting/invoices", tags=["accounting"])
def accounting_invoice_list(invoice_type: Optional[str] = None, status: Optional[str] = None,
                            counterparty: Optional[str] = None, property_id: Optional[str] = None,
                            overdue_only: bool = False, limit: int = 50) -> Any:
    """List invoices with balances and overdue flags."""
    return j(core.accounting_invoice_list(invoice_type=invoice_type, status=status,
                                          counterparty=counterparty, property_id=property_id,
                                          overdue_only=overdue_only, limit=limit))


@app.get("/accounting/invoices/{invoice_id}", tags=["accounting"])
def accounting_invoice_get(invoice_id: str) -> Any:
    """Fetch one invoice with its payments."""
    return j(core.accounting_invoice_get(invoice_id))


@app.post("/accounting/invoices/{invoice_id}/post", tags=["accounting"])
def accounting_invoice_post(invoice_id: str) -> Any:
    """Post an invoice to the ledger."""
    return j(core.accounting_invoice_post(invoice_id))


@app.post("/accounting/payments", tags=["accounting"], status_code=201)
def accounting_payment_record(payload: PaymentRequest) -> Any:
    """Record a receipt or disbursement and allocate it to an invoice."""
    return j(core.accounting_payment_record(**payload.model_dump(exclude_none=True)))


@app.post("/accounting/expenses", tags=["accounting"], status_code=201)
def accounting_expense_create(payload: ExpenseRequest) -> Any:
    """Capture an expense."""
    return j(core.accounting_expense_create(**payload.model_dump(exclude_none=True)))


@app.get("/accounting/aging", tags=["accounting"])
def accounting_invoice_aging(as_of: Optional[str] = None, invoice_type: Optional[str] = None) -> Any:
    """Receivable/payable ageing buckets."""
    return j(core.accounting_invoice_aging(as_of, invoice_type))


@app.post("/accounting/leases", tags=["accounting"], status_code=201)
def accounting_lease_create(payload: LeaseRequest) -> Any:
    """Create a lease."""
    return j(core.accounting_lease_create(**payload.model_dump(exclude_none=True)))


@app.get("/accounting/leases", tags=["accounting"])
def accounting_lease_list(status: Optional[str] = None, property_id: Optional[str] = None,
                          scheme_id: Optional[str] = None, city_id: Optional[str] = None) -> Any:
    """List leases."""
    return j(core.accounting_lease_list(status=status, property_id=property_id,
                                        scheme_id=scheme_id, city_id=city_id))


@app.get("/accounting/rent-roll", tags=["accounting"])
def accounting_rent_roll(as_of: Optional[str] = None) -> Any:
    """Rent roll of active leases."""
    return j(core.accounting_rent_roll(as_of))


@app.post("/accounting/rent-invoices", tags=["accounting"], status_code=201)
def accounting_generate_rent_invoices(payload: RentInvoiceRequest) -> Any:
    """Raise this period's rent invoices for every due lease."""
    return j(core.accounting_generate_rent_invoices(**payload.model_dump(exclude_none=True)))


@app.post("/accounting/budgets", tags=["accounting"], status_code=201)
def accounting_budget_create(payload: BudgetRequest) -> Any:
    """Create a budget."""
    return j(core.accounting_budget_create(**payload.model_dump(exclude_none=True)))


@app.get("/accounting/budgets", tags=["accounting"])
def accounting_budget_list() -> Any:
    """List budgets."""
    return j(core.accounting_budget_list())


@app.get("/accounting/budgets/{budget_id}/variance", tags=["accounting"])
def accounting_budget_variance(budget_id: str) -> Any:
    """Budget vs actual variance."""
    return j(core.accounting_budget_variance(budget_id))


@app.get("/accounting/properties/{property_id}/performance", tags=["accounting"])
def accounting_property_performance(property_id: str, from_date: Optional[str] = None,
                                    to_date: Optional[str] = None) -> Any:
    """Property-level P&L, rent roll and yields."""
    return j(core.accounting_property_performance(property_id, from_date, to_date))


# ------------------------------------------------------------------
# Finance / ROI
# ------------------------------------------------------------------


class InvestmentMetricsRequest(BaseModel):
    cashflows: List[float]
    discount_rate: Optional[float] = None


class RoiRequest(BaseModel):
    initial_investment: float
    annual_cash_flow: float = 0.0
    hold_years: Optional[int] = None
    terminal_value: float = 0.0
    discount_rate: Optional[float] = None
    annual_growth: float = 0.0
    annual_cost_inflation: float = 0.0
    loan_amount: float = 0.0
    loan_rate: Optional[float] = None
    loan_years: Optional[int] = None


class PropertyRoiRequest(BaseModel):
    purchase_price: float
    annual_rent: float = 0.0
    annual_expenses: float = 0.0
    hold_years: Optional[int] = None
    appreciation_rate: float = 0.075
    discount_rate: Optional[float] = None
    down_payment_share: float = 1.0
    loan_rate: Optional[float] = None
    loan_years: Optional[int] = None
    selling_cost_rate: float = 0.02


@app.get("/finance/mortgage", tags=["finance"])
def finance_mortgage_calculator(principal: float, annual_rate: Optional[float] = None,
                                years: Optional[int] = None, payments_per_year: int = 12) -> Any:
    """Amortising mortgage: payment, total interest and schedule."""
    return j(core.finance_mortgage_calculator(principal, annual_rate=annual_rate, years=years,
                                              payments_per_year=payments_per_year))


@app.post("/finance/investment-metrics", tags=["finance"])
def finance_investment_metrics(payload: InvestmentMetricsRequest) -> Any:
    """NPV / IRR / payback / PI / equity multiple for a cash-flow series."""
    return j(core.finance_investment_metrics(payload.cashflows, payload.discount_rate))


@app.get("/finance/cap-rate", tags=["finance"])
def finance_cap_rate(noi: float, value: float) -> Any:
    """Capitalisation rate from NOI and value."""
    return j(core.finance_cap_rate(noi, value))


@app.get("/finance/cash-on-cash", tags=["finance"])
def finance_cash_on_cash(annual_cash_flow: float, cash_invested: float) -> Any:
    """Cash-on-cash return."""
    return j(core.finance_cash_on_cash(annual_cash_flow, cash_invested))


@app.post("/finance/roi", tags=["finance"])
def finance_roi_analysis(payload: RoiRequest) -> Any:
    """Leveraged ROI analysis with scenarios."""
    return j(core.finance_roi_analysis(**payload.model_dump(exclude_none=True)))


@app.post("/finance/property-roi", tags=["finance"])
def finance_property_roi(payload: PropertyRoiRequest) -> Any:
    """Property ROI: yields, appreciation, leverage, IRR and exit proceeds."""
    return j(core.finance_property_roi(**payload.model_dump(exclude_none=True)))


@app.get("/finance/rental-yield/{property_id}", tags=["finance"])
def finance_rental_yield(property_id: str, annual_rent: Optional[float] = None,
                         annual_expenses: float = 0.0) -> Any:
    """Gross/net rental yield and cap rate for a property."""
    return j(core.finance_rental_yield(property_id, annual_rent=annual_rent, annual_expenses=annual_expenses))


@app.get("/finance/portfolio-roi", tags=["finance"])
def finance_portfolio_roi(discount_rate: Optional[float] = None, hold_years: int = 5,
                          appreciation_rate: float = 0.075, city: Optional[str] = None,
                          scheme: Optional[str] = None) -> Any:
    """Portfolio-level leveraged ROI."""
    return j(core.finance_portfolio_roi(discount_rate=discount_rate, hold_years=hold_years,
                                        appreciation_rate=appreciation_rate, city=city, scheme=scheme))


# ==================================================================
# POINTS OF INTEREST (POI)
# ==================================================================


class PoiCreateRequest(BaseModel):
    name: str
    latitude: float
    longitude: float
    category: str = "other"
    subcategory: Optional[str] = None
    address: Optional[str] = None
    city_id: Optional[str] = None
    scheme_id: Optional[str] = None
    block_zone_area_id: Optional[str] = None
    rating: Optional[float] = None
    importance: float = 1.0
    tags: Optional[List[str]] = None
    source: str = "manual"


class PoiUpdateRequest(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    address: Optional[str] = None
    rating: Optional[float] = None
    importance: Optional[float] = None
    tags: Optional[List[str]] = None


class PoiPolygonRequest(BaseModel):
    coordinates: List[List[float]]
    category: Optional[str] = None


@app.post("/poi", tags=["poi"], status_code=201)
def poi_add(payload: PoiCreateRequest) -> Any:
    """Register a point of interest."""
    return j(core.poi_add(**payload.model_dump(exclude_none=True)))


@app.get("/poi", tags=["poi"])
def poi_list(category: Optional[str] = None, city: Optional[str] = None, scheme: Optional[str] = None,
             query: Optional[str] = None, limit: int = 100) -> Any:
    """List points of interest."""
    return j(core.poi_list(category=category, city=city, scheme=scheme, query=query, limit=limit))


@app.get("/poi/categories", tags=["poi"])
def poi_categories() -> Any:
    """POI categories with counts and weights."""
    return j(core.poi_categories())


@app.get("/poi/nearby", tags=["poi"])
def poi_nearby(latitude: float, longitude: float, radius_km: float = 2.0,
               category: Optional[str] = None, limit: int = 50) -> Any:
    """Points of interest within a radius of a point."""
    return j(core.poi_nearby(latitude, longitude, radius_km=radius_km, category=category, limit=limit))


@app.get("/poi/nearest", tags=["poi"])
def poi_nearest(latitude: float, longitude: float, radius_km: float = 25.0) -> Any:
    """Nearest POI in every category."""
    return j(core.poi_nearest(latitude, longitude, radius_km=radius_km))


@app.get("/poi/density/{entity_type}/{entity_id}", tags=["poi"])
def poi_density(entity_type: str, entity_id: str) -> Any:
    """POI mix and density inside an entity's footprint."""
    return j(core.poi_density(entity_type, entity_id))


@app.get("/poi/accessibility", tags=["poi"])
def poi_accessibility(entity_type: Optional[str] = None, entity_id: Optional[str] = None,
                      latitude: Optional[float] = None, longitude: Optional[float] = None,
                      radius_km: float = 3.0) -> Any:
    """Distance-decayed liveability score (0-100)."""
    return j(core.poi_accessibility_score(entity_type=entity_type, entity_id=entity_id,
                                          latitude=latitude, longitude=longitude, radius_km=radius_km))


@app.get("/poi/map", tags=["poi"], response_class=HTMLResponse)
def poi_map(entity_type: Optional[str] = None, entity_id: Optional[str] = None,
            latitude: Optional[float] = None, longitude: Optional[float] = None,
            radius_km: float = 2.0, limit: int = 60, base_map: Optional[str] = None,
            lang: str = Depends(ui_lang), theme: str = Depends(ui_theme)) -> HTMLResponse:
    """HTML map of points of interest."""
    return HTMLResponse(content=core.poi_map(entity_type=entity_type, entity_id=entity_id,
                                             latitude=latitude, longitude=longitude, radius_km=radius_km,
                                             limit=limit, base_map=base_map, lang=lang, theme=theme))


@app.post("/poi/within-polygon", tags=["poi"])
def poi_within_polygon(payload: PoiPolygonRequest) -> Any:
    """Points of interest inside a polygon."""
    return j(core.poi_within_polygon(payload.coordinates, payload.category))


@app.get("/poi/route", tags=["poi"])
def poi_route(origin_poi: str, destination_poi: str, mode: str = "drive",
              alternatives: int = 2, traffic_factor: Optional[float] = None,
              network: Optional[str] = None) -> Any:
    """Best route (plus alternatives) between two POIs, fitting the travel mode."""
    return j(core.poi_route(origin_poi, destination_poi, mode=mode, alternatives=alternatives,
                            traffic_factor=traffic_factor, network=network))


@app.get("/poi/{poi_id}", tags=["poi"])
def poi_get(poi_id: str) -> Any:
    """Fetch one point of interest."""
    return j(core.poi_get(poi_id))


@app.put("/poi/{poi_id}", tags=["poi"])
def poi_update(poi_id: str, payload: PoiUpdateRequest) -> Any:
    """Update a point of interest."""
    return j(core.poi_update(poi_id, **payload.model_dump(exclude_none=True)))


@app.delete("/poi/{poi_id}", tags=["poi"])
def poi_delete(poi_id: str) -> Any:
    """Delete a point of interest."""
    return j(core.poi_delete(poi_id))


# ==================================================================
# AREAS OF INTEREST (AOI)
# ==================================================================


class AoiCreateRequest(BaseModel):
    name: str
    kind: str = "circle"
    description: Optional[str] = None
    center_latitude: Optional[float] = None
    center_longitude: Optional[float] = None
    radius_m: Optional[float] = None
    coordinates: Optional[List[List[float]]] = None
    bounds: Optional[Dict[str, float]] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    city: Optional[str] = None
    scheme: Optional[str] = None
    tags: Optional[List[str]] = None
    watch_categories: Optional[List[str]] = None
    watch_alert_threshold: float = 0.0
    created_by: Optional[str] = None
    notes: Optional[str] = None


class AoiUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    watch_categories: Optional[List[str]] = None
    watch_alert_threshold: Optional[float] = None
    notes: Optional[str] = None


class AoiCompareRequest(BaseModel):
    aoi_ids: List[str]


@app.post("/aoi", tags=["aoi"], status_code=201)
def aoi_create(payload: AoiCreateRequest) -> Any:
    """Save an area of interest."""
    return j(core.aoi_create(**payload.model_dump(exclude_none=True)))


@app.get("/aoi", tags=["aoi"])
def aoi_list(kind: Optional[str] = None, city: Optional[str] = None, scheme: Optional[str] = None) -> Any:
    """List saved areas of interest."""
    return j(core.aoi_list(kind=kind, city=city, scheme=scheme))


@app.post("/aoi/compare", tags=["aoi"])
def aoi_compare(payload: AoiCompareRequest) -> Any:
    """Compare areas of interest side by side."""
    return j(core.aoi_compare(payload.aoi_ids))


@app.get("/aoi/{aoi_id}", tags=["aoi"])
def aoi_get(aoi_id: str) -> Any:
    """Fetch one area of interest."""
    return j(core.aoi_get(aoi_id))


@app.put("/aoi/{aoi_id}", tags=["aoi"])
def aoi_update(aoi_id: str, payload: AoiUpdateRequest) -> Any:
    """Update an area of interest."""
    return j(core.aoi_update(aoi_id, **payload.model_dump(exclude_none=True)))


@app.delete("/aoi/{aoi_id}", tags=["aoi"])
def aoi_delete(aoi_id: str) -> Any:
    """Delete an area of interest."""
    return j(core.aoi_delete(aoi_id))


@app.get("/aoi/{aoi_id}/stats", tags=["aoi"])
def aoi_stats(aoi_id: str) -> Any:
    """Quick statistics for an area of interest."""
    return j(core.aoi_stats(aoi_id))


@app.get("/aoi/{aoi_id}/analyze", tags=["aoi"])
def aoi_analyze(aoi_id: str, years: int = 5) -> Any:
    """Full analytics for an area of interest."""
    return j(core.aoi_analyze(aoi_id, years=years))


@app.get("/aoi/{aoi_id}/watch", tags=["aoi"])
def aoi_watch(aoi_id: str, days: int = 120) -> Any:
    """News watch for an area of interest."""
    return j(core.aoi_watch(aoi_id, days=days))


@app.get("/aoi/{aoi_id}/report", tags=["aoi"], response_class=HTMLResponse)
def aoi_report(aoi_id: str, years: int = 5, include_map: bool = True, include_news: bool = True,
               lang: str = Depends(ui_lang), theme: str = Depends(ui_theme)) -> HTMLResponse:
    """Printable HTML report for an area of interest."""
    return HTMLResponse(content=core.aoi_report(aoi_id, years=years, include_map=include_map,
                                                include_news=include_news, lang=lang, theme=theme))


@app.get("/aoi/{aoi_id}/map", tags=["aoi"], response_class=HTMLResponse)
def aoi_map(aoi_id: str, base_map: Optional[str] = None, include_properties: bool = True,
            include_pois: bool = True, lang: str = Depends(ui_lang),
            theme: str = Depends(ui_theme)) -> HTMLResponse:
    """HTML map of an area of interest."""
    return HTMLResponse(content=core.aoi_map(aoi_id, base_map=base_map, include_properties=include_properties,
                                             include_pois=include_pois, lang=lang, theme=theme))


# ==================================================================
# PORTAL: discovery, settings, federated search and statistics
# ==================================================================


class SettingsUpdateRequest(BaseModel):
    updates: Dict[str, Any]


@app.get("/portal/health", tags=["portal"])
def portal_health() -> Any:
    """Liveness snapshot."""
    return j(core.portal_health())


@app.get("/portal/catalog", tags=["portal"])
def portal_catalog(include_parameters: bool = False, group: Optional[str] = None) -> Any:
    """Inventory of every MCP tool, resource and prompt."""
    return j(core.portal_catalog(include_parameters=include_parameters, group=group))


@app.get("/portal/schema", tags=["portal"])
def portal_schema(model: Optional[str] = None) -> Any:
    """JSON schema for a portal model (or the model list)."""
    return j(core.portal_schema(model))


# ------------------------------------------------------------------
# Administration › Property database (properties.manage)
# ------------------------------------------------------------------


class PropertyBulk(BaseModel):
    ids: List[str] = Field(..., min_length=1, max_length=1000)
    action: str  # feature | unfeature | status | assign_agent | delete
    value: Optional[str] = None


class PropertyImport(BaseModel):
    csv: str = Field(..., min_length=5, max_length=20_000_000)
    dry_run: bool = True


@app.get("/admin/properties", tags=["admin"])
def admin_properties(q: str = "", city_id: str = "", scheme_id: str = "", status: str = "", category: str = "",
                     use_type: str = "", featured: Optional[bool] = None, agent_id: str = "", located: Optional[bool] = None,
                     min_price: Optional[float] = None, max_price: Optional[float] = None, sort: str = "updated",
                     order: str = "desc", page: int = 1, page_size: int = 25) -> Any:
    """Every listing with every field: search, filters, sorting, paging and facet counts."""
    return property_admin.query(q, city_id, scheme_id, status, category, use_type, featured, agent_id, located,
                                min_price, max_price, sort, order, page, page_size)


@app.get("/admin/properties/meta", tags=["admin"])
def admin_properties_meta() -> Any:
    """Choices for the property form: statuses, categories, cities, schemes, blocks and agents."""
    return {
        "statuses": property_admin.STATUSES, "categories": property_admin.CATEGORIES, "use_types": property_admin.USE_TYPES,
        "cities": [{"id": c.id, "name": c.name} for c in priority.sort_cities(list(core.cities_db))],
        "schemes": [{"id": s.id, "name": s.name, "city_id": s.city_id}
                    for s in sorted(core.housing_schemes_db, key=priority.society_sort_key_for(core))],
        "blocks": [{"id": b.id, "name": b.name, "scheme_id": b.scheme_id} for b in sorted(core.block_zone_areas_db, key=lambda b: b.name)],
        "agents": [{"id": a.id, "name": a.name} for a in sorted(core.agents_db, key=lambda a: a.name)],
    }


@app.get("/admin/properties/export.csv", tags=["admin"])
def admin_properties_export(q: str = "", city_id: str = "", status: str = "", category: str = "") -> Any:
    """The (filtered) catalogue as a spreadsheet; re-import it after editing."""
    rows = property_admin.query(q, city_id, "", status, category, page_size=200, page=1)
    everything: List[Dict[str, Any]] = list(rows["rows"])
    for page in range(2, rows["pages"] + 1):
        everything += property_admin.query(q, city_id, "", status, category, page_size=200, page=page)["rows"]
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    return Response(content=property_admin.export_csv(everything), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="arzepak-properties-{stamp}.csv"'})


@app.post("/admin/properties/import", tags=["admin"])
def admin_properties_import(payload: PropertyImport) -> Any:
    """Create / update listings from a CSV (same columns as the export). Checks every row first;
    nothing is saved if any row is invalid, or while ``dry_run`` is on."""
    try:
        return property_admin.import_csv(payload.csv, dry_run=payload.dry_run)
    except property_admin.Invalid as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/admin/properties/bulk", tags=["admin"])
def admin_properties_bulk(payload: PropertyBulk) -> Any:
    try:
        return property_admin.bulk(payload.ids, payload.action, payload.value)
    except property_admin.Invalid as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/admin/properties/{property_id}", tags=["admin"])
def admin_property(property_id: str) -> Any:
    r = property_admin.get(property_id)
    if not r:
        raise HTTPException(status_code=404, detail=f"Property not found: {property_id}")
    return r


@app.post("/admin/properties", tags=["admin"], status_code=201)
def admin_property_create(payload: Dict[str, Any]) -> Any:
    try:
        return property_admin.save(payload)
    except property_admin.Invalid as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.put("/admin/properties/{property_id}", tags=["admin"])
def admin_property_update(property_id: str, payload: Dict[str, Any]) -> Any:
    try:
        return property_admin.save(payload, property_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Property not found: {property_id}")
    except property_admin.Invalid as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.delete("/admin/properties/{property_id}", tags=["admin"])
def admin_property_delete(property_id: str) -> Any:
    result = j(core.delete_property(property_id))
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/portal/storage", tags=["portal"])
def portal_storage_status() -> Any:
    """Where the portal's data is saved (PostgreSQL or SQLite), when it last saved and how many
    rows each store holds."""
    st = storage.instance()
    if st is None:
        return {"enabled": False, "note": "Persistence is off (PORTAL_PERSIST=0): data lives in memory only."}
    return {"enabled": True, **st.status()}


@app.post("/portal/storage/flush", tags=["portal"])
def portal_storage_flush() -> Any:
    """Save every pending change now."""
    st = storage.instance()
    if st is None:
        raise HTTPException(status_code=409, detail="Persistence is off (PORTAL_PERSIST=0)")
    return {"saved": True, **st.flush()}


@app.get("/portal/settings", tags=["portal"])
def portal_settings_get() -> Any:
    """Read runtime settings."""
    return j(core.portal_settings("get"))


@app.put("/portal/settings", tags=["portal"])
def portal_settings_update(payload: SettingsUpdateRequest) -> Any:
    """Update runtime settings (assumptions / forecast / accounting / auth)."""
    return j(core.portal_settings("update", payload.updates))


@app.get("/portal/audit", tags=["portal"])
def portal_audit_log(limit: int = 50) -> Any:
    """Unified activity trail."""
    return j(core.portal_audit_log(limit=limit))


_SEARCH_GROUP_PERMISSION = {
    "leads": "crm.view", "customers": "crm.view", "deals": "crm.view", "transactions": "crm.view",
    "pmo_projects": "projects.view", "pmo_tasks": "projects.view", "pmo_risks": "projects.view",
    "msg_conversations": "audit.view", "msg_messages": "audit.view", "msg_actions": "audit.view",
}


@app.get("/portal/search", tags=["portal"])
def global_search(query: str, limit: int = 10) -> Any:
    """Federated search across the whole portal. Private groups (CRM, projects, team messages) are
    only included for users whose role may see them."""
    data = j(core.global_search(query, limit=max(1, min(limit, 50))))
    me = access.current()
    results = data.get("results") or {}
    for group, perm in _SEARCH_GROUP_PERMISSION.items():
        if group in results and not access.can(me, perm):
            results.pop(group)
    data["total"] = sum(len(v) for v in results.values() if isinstance(v, list))
    return data


@app.get("/portal/statistics", tags=["portal"])
def portal_statistics() -> Any:
    """Portfolio-wide statistics."""
    return j(core.portal_statistics())


@app.get("/portal/availability", tags=["portal"])
def property_availability(city: Optional[str] = None, scheme: Optional[str] = None,
                          use_type: Optional[str] = None, category: Optional[str] = None,
                          status: Optional[str] = None, limit: int = 50) -> Any:
    """Availability breakdown of the listing book."""
    return j(core.property_availability(city=city, scheme=scheme, use_type=use_type, category=category,
                                        status=status, limit=limit))


@app.get("/portal/market-trends", tags=["portal"])
def market_trends(city: Optional[str] = None, scheme: Optional[str] = None, years: int = 5,
                  days: int = 180) -> Any:
    """Market trends for a city or scheme."""
    return j(core.market_trends(city=city, scheme=scheme, years=years, days=days))


@app.get("/portal/home", tags=["portal"], response_class=HTMLResponse)
def portal_home(lang: str = Depends(ui_lang), theme: str = Depends(ui_theme),
                city: Optional[str] = None, scheme: Optional[str] = None,
                include_ticker: bool = True, include_stats: bool = True) -> HTMLResponse:
    """The public portal home page (HTML): content, stories, contacts and ad sections."""
    return HTMLResponse(content=core.content_portal_home(
        lang=lang, theme=theme, city=city, scheme=scheme,
        include_ticker=include_ticker, include_stats=include_stats))


@app.get("/portal/home.html", tags=["portal"], response_class=HTMLResponse)
def portal_home_html(lang: str = Depends(ui_lang), theme: str = Depends(ui_theme),
                     city: Optional[str] = None, scheme: Optional[str] = None) -> HTMLResponse:
    """Alias of ``/portal/home`` that always serves HTML (for direct browsing)."""
    return HTMLResponse(content=core.content_portal_home(lang=lang, theme=theme, city=city, scheme=scheme))


# ==================================================================
# ROUTING: on foot / bicycle / motor car — best & alternative routes
# ==================================================================


class RoadNetworkCreateRequest(BaseModel):
    name: str
    ways: Optional[List[Dict[str, Any]]] = None
    description: Optional[str] = None


class RouteMatrixRequest(BaseModel):
    poi_ids: Optional[List[str]] = None
    coordinates: Optional[List[List[float]]] = None
    mode: str = "drive"
    city: Optional[str] = None
    scheme: Optional[str] = None
    network: Optional[str] = None


@app.get("/gis/travel-modes", tags=["routing"])
def gis_travel_modes() -> Any:
    """Available travel modes (on foot, bicycle, motor car) and their road speeds."""
    return j(core.gis_travel_modes())


@app.get("/gis/road-classes", tags=["routing"])
def gis_road_classes() -> Any:
    """Road classes with their per-mode speeds."""
    return j(core.gis_road_classes())


@app.get("/gis/road-networks", tags=["routing"])
def gis_road_networks() -> Any:
    """List the road networks available for routing."""
    return j(core.gis_list_road_networks())


@app.post("/gis/road-networks", tags=["routing"], status_code=201)
def gis_road_network_create(payload: RoadNetworkCreateRequest) -> Any:
    """Register a custom routable road network from polyline ``ways``."""
    return j(core.gis_add_road_network(**payload.model_dump(exclude_none=True)))


@app.get("/gis/route/compare", tags=["routing"])
def gis_route_compare(origin_latitude: float, origin_longitude: float,
                      destination_latitude: float, destination_longitude: float,
                      modes: Optional[str] = None, city: Optional[str] = None,
                      scheme: Optional[str] = None, network: Optional[str] = None) -> Any:
    """Compare every travel mode between two points (comma-separated ``modes`` optional)."""
    mode_list = [m.strip() for m in modes.split(",") if m.strip()] if modes else None
    return j(core.gis_route_compare(origin_latitude, origin_longitude, destination_latitude,
                                    destination_longitude, modes=mode_list, city=city,
                                    scheme=scheme, network=network))


@app.post("/gis/route/matrix", tags=["routing"])
def gis_route_matrix(payload: RouteMatrixRequest) -> Any:
    """Distance/time matrix between POIs or coordinates."""
    return j(core.gis_route_matrix(**payload.model_dump(exclude_none=True)))


@app.get("/gis/route/map", tags=["routing"], response_class=HTMLResponse)
def gis_route_map(origin_latitude: float, origin_longitude: float,
                  destination_latitude: float, destination_longitude: float,
                  mode: str = "drive", alternatives: int = 2, include_compare: bool = True,
                  ticker: bool = False, base_map: Optional[str] = None, city: Optional[str] = None,
                  scheme: Optional[str] = None, network: Optional[str] = None,
                  lang: str = Depends(ui_lang), theme: str = Depends(ui_theme)) -> HTMLResponse:
    """HTML map of the best route and its alternatives."""
    return HTMLResponse(content=core.gis_route_map(
        origin_latitude, origin_longitude, destination_latitude, destination_longitude,
        mode=mode, alternatives=alternatives, include_compare=include_compare, ticker=ticker,
        base_map=base_map, city=city, scheme=scheme, network=network, lang=lang, theme=theme))


@app.get("/gis/route", tags=["routing"])
def gis_route(origin_latitude: float, origin_longitude: float,
              destination_latitude: float, destination_longitude: float,
              mode: str = "drive", alternatives: int = 2, traffic_factor: Optional[float] = None,
              city: Optional[str] = None, scheme: Optional[str] = None,
              network: Optional[str] = None, origin_label: Optional[str] = None,
              destination_label: Optional[str] = None) -> Any:
    """Best route (plus alternatives) between two points, on foot or by car."""
    return j(core.gis_route(origin_latitude, origin_longitude, destination_latitude,
                            destination_longitude, mode=mode, alternatives=alternatives,
                            traffic_factor=traffic_factor, city=city, scheme=scheme,
                            network=network, origin_label=origin_label,
                            destination_label=destination_label))


# ==================================================================
# CONTENT: pages, history, contacts and success stories
# ==================================================================


class ContentPageCreateRequest(BaseModel):
    key: str
    title: str
    category: str = "about"
    subtitle: Optional[str] = None
    summary: Optional[str] = None
    body: Optional[List[str]] = None
    highlights: Optional[List[Dict[str, str]]] = None
    bullets: Optional[List[str]] = None
    faqs: Optional[List[Dict[str, str]]] = None
    tags: Optional[List[str]] = None
    nav_label: Optional[str] = None
    show_in_nav: bool = True
    order: int = 100
    status: str = "published"


class ContentPageUpdateRequest(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    subtitle: Optional[str] = None
    summary: Optional[str] = None
    body: Optional[List[str]] = None
    highlights: Optional[List[Dict[str, str]]] = None
    bullets: Optional[List[str]] = None
    faqs: Optional[List[Dict[str, str]]] = None
    tags: Optional[List[str]] = None
    nav_label: Optional[str] = None
    show_in_nav: Optional[bool] = None
    order: Optional[int] = None
    status: Optional[str] = None


class HistoryCreateRequest(BaseModel):
    year: int
    title: str
    description: str
    kind: str = "milestone"
    month: Optional[int] = None
    tags: Optional[List[str]] = None
    featured: bool = False


class ContactCreateRequest(BaseModel):
    channel_type: str
    label: str
    value: str
    url: Optional[str] = None
    hours: Optional[str] = None
    city: Optional[str] = None
    scheme: Optional[str] = None
    region: Optional[str] = None
    priority: int = 100
    is_primary: bool = False
    notes: Optional[str] = None


class StoryCreateRequest(BaseModel):
    title: str
    story_type: str = "case_study"
    client_name: Optional[str] = None
    client_role: Optional[str] = None
    quote: Optional[str] = None
    rating: Optional[float] = None
    location: Optional[str] = None
    city: Optional[str] = None
    scheme: Optional[str] = None
    property_id: Optional[str] = None
    project_id: Optional[str] = None
    narrative: Optional[List[str]] = None
    metrics: Optional[List[Dict[str, str]]] = None
    highlights: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    featured: bool = False
    date: Optional[str] = None


@app.get("/content/overview", tags=["content"])
def content_overview() -> Any:
    """Counts and breakdowns for pages, history, contacts, stories and ads."""
    return j(core.content_overview())


@app.get("/content/pages", tags=["content"])
def content_page_list(category: Optional[str] = None, tag: Optional[str] = None,
                      status: str = "published", nav_only: bool = False) -> Any:
    """List portal content pages."""
    return j(core.content_page_list(category=category, tag=tag, status=status, nav_only=nav_only))


@app.post("/content/pages", tags=["content"], status_code=201)
def content_page_create(payload: ContentPageCreateRequest) -> Any:
    """Create a portal content page."""
    return j(core.content_page_create(**payload.model_dump(exclude_none=True)))


@app.get("/content/pages/{key}", tags=["content"])
def content_page_get(key: str) -> Any:
    """Fetch one content page by key."""
    return j(core.content_page_get(key))


@app.put("/content/pages/{key}", tags=["content"])
def content_page_update(key: str, payload: ContentPageUpdateRequest) -> Any:
    """Update a portal content page."""
    return j(core.content_page_update(key, **payload.model_dump(exclude_none=True)))


@app.delete("/content/pages/{key}", tags=["content"])
def content_page_delete(key: str) -> Any:
    """Delete a portal content page."""
    return j(core.content_page_delete(key))


@app.get("/content/history", tags=["content"])
def content_history(kind: Optional[str] = None, since: Optional[int] = None,
                    until: Optional[int] = None, featured: Optional[bool] = None) -> Any:
    """The company-history timeline."""
    return j(core.content_history(kind=kind, since=since, until=until, featured=featured))


@app.post("/content/history", tags=["content"], status_code=201)
def content_history_add(payload: HistoryCreateRequest) -> Any:
    """Add a company-history entry."""
    return j(core.content_history_add(**payload.model_dump(exclude_none=True)))


@app.get("/content/contacts", tags=["content"])
def content_contact(channel_type: Optional[str] = None, city: Optional[str] = None,
                    scheme: Optional[str] = None, primary_only: bool = False) -> Any:
    """The contact directory."""
    return j(core.content_contact(channel_type=channel_type, city=city, scheme=scheme,
                                  primary_only=primary_only))


@app.post("/content/contacts", tags=["content"], status_code=201)
def content_contact_add(payload: ContactCreateRequest) -> Any:
    """Add a contact channel."""
    return j(core.content_contact_add(**payload.model_dump(exclude_none=True)))


@app.get("/content/stories", tags=["content"])
def content_stories(story_type: Optional[str] = None, city: Optional[str] = None,
                    scheme: Optional[str] = None, featured: Optional[bool] = None,
                    tag: Optional[str] = None) -> Any:
    """Success stories, case studies and testimonials."""
    return j(core.content_success_stories(story_type=story_type, city=city, scheme=scheme,
                                          featured=featured, tag=tag))


@app.post("/content/stories", tags=["content"], status_code=201)
def content_story_add(payload: StoryCreateRequest) -> Any:
    """Publish a success story."""
    return j(core.content_success_story_add(**payload.model_dump(exclude_none=True)))


@app.get("/content/navigation", tags=["content"])
def content_navigation() -> Any:
    """The portal navigation menu."""
    return j(core.content_navigation())


@app.get("/content/site", tags=["content"])
def content_site(lang: str = "en", city: Optional[str] = None, scheme: Optional[str] = None) -> Any:
    """The complete portal site payload (nav, blocks, content, resolved ads)."""
    return j(core.content_site(lang=lang, city=city, scheme=scheme))


# ==================================================================
# ADVERTISING
# ==================================================================


class AdCreateRequest(BaseModel):
    title: str
    headline: str
    advertiser: str = ""
    category: str = "services"
    slot: str = "infeed"
    body: Optional[str] = None
    keywords: Optional[List[str]] = None
    cta_label: Optional[str] = None
    cta_url: Optional[str] = None
    media_url: Optional[str] = None
    image_url: Optional[str] = None
    tags: Optional[List[str]] = None
    contact: Optional[str] = None
    phone: Optional[str] = None
    price_text: Optional[str] = None
    offer: Optional[str] = None
    city: Optional[str] = None
    scheme: Optional[str] = None
    lang: Optional[str] = None
    priority: int = 100
    weight: float = 1.0
    status: str = "active"
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    budget: float = 0.0
    pricing: str = "flat"
    rate: float = 0.0


class AdUpdateRequest(BaseModel):
    title: Optional[str] = None
    headline: Optional[str] = None
    body: Optional[str] = None
    advertiser: Optional[str] = None
    category: Optional[str] = None
    slot: Optional[str] = None
    keywords: Optional[List[str]] = None
    cta_label: Optional[str] = None
    cta_url: Optional[str] = None
    image_url: Optional[str] = None
    tags: Optional[List[str]] = None
    contact: Optional[str] = None
    phone: Optional[str] = None
    price_text: Optional[str] = None
    offer: Optional[str] = None
    city: Optional[str] = None
    scheme: Optional[str] = None
    lang: Optional[str] = None
    priority: Optional[int] = None
    weight: Optional[float] = None
    status: Optional[str] = None
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    budget: Optional[float] = None
    pricing: Optional[str] = None
    rate: Optional[float] = None


class AdEventRequest(BaseModel):
    event: str = "impression"


@app.get("/ads/config", tags=["ads"])
def ad_config() -> Any:
    """Ad setup for the apps: direct (sponsored) ads, plus Google AdSense (web) and
    AdMob (Android / iOS) to fill slots no advertiser has bought."""
    cfg = core.content.ADS_CONFIG
    return ads_network.config(cfg["house_ad_title"], cfg["house_ad_body"], cfg["sponsored_label"])


@app.get("/ads.txt", tags=["ads"], response_class=PlainTextResponse)
def ads_txt() -> PlainTextResponse:
    """The ads.txt file Google requires at the web site's root (when AdSense is set up)."""
    body = ads_network.ads_txt()
    if body is None:
        raise HTTPException(status_code=404, detail="AdSense is not configured (ADS_ADSENSE_CLIENT)")
    return PlainTextResponse(body)


@app.get("/ads/categories", tags=["ads"])
def ad_categories() -> Any:
    """Advertisement categories."""
    return j(core.ad_categories())


@app.get("/ads/slots", tags=["ads"])
def ad_slots() -> Any:
    """Advertisement slots."""
    return j(core.ad_slots())


@app.get("/ads/active", tags=["ads"])
def ad_active(slot: Optional[str] = None, category: Optional[str] = None, city: Optional[str] = None,
              scheme: Optional[str] = None, lang: Optional[str] = None, limit: Optional[int] = None) -> Any:
    """Live, in-window, on-target creatives (weighted rotation)."""
    return j(core.ad_active(slot=slot, category=category, city=city, scheme=scheme, lang=lang, limit=limit))


@app.get("/ads/performance", tags=["ads"])
def ad_performance(ad_id: Optional[str] = None) -> Any:
    """Impression / click / CTR performance for one ad or the whole book."""
    return j(core.ad_performance(ad_id))


@app.get("/ads/section", tags=["ads"])
def ad_section(slot: str = "infeed", category: Optional[str] = None, city: Optional[str] = None,
               scheme: Optional[str] = None, lang: Optional[str] = None, limit: Optional[int] = None) -> Any:
    """A ready-to-render advertisement section."""
    return j(core.ad_section(slot=slot, category=category, city=city, scheme=scheme, lang=lang, limit=limit))


@app.get("/ads/preview", tags=["ads"], response_class=HTMLResponse)
def ad_preview(slot: str = "infeed", category: Optional[str] = None, city: Optional[str] = None,
               scheme: Optional[str] = None, limit: Optional[int] = None,
               lang: str = Depends(ui_lang), theme: str = Depends(ui_theme)) -> HTMLResponse:
    """HTML preview of an advertisement slot."""
    return HTMLResponse(content=core.ad_preview(slot=slot, category=category, city=city,
                                                scheme=scheme, limit=limit, lang=lang, theme=theme))


@app.get("/ads/report", tags=["ads"], response_class=HTMLResponse)
def ad_report(lang: str = Depends(ui_lang), theme: str = Depends(ui_theme)) -> HTMLResponse:
    """Printable advertising report (all slots + delivery performance)."""
    return HTMLResponse(content=core.ad_report(lang=lang, theme=theme))


@app.get("/ads", tags=["ads"])
def ad_list(category: Optional[str] = None, slot: Optional[str] = None, status: Optional[str] = None,
            advertiser: Optional[str] = None, tag: Optional[str] = None, limit: int = 100) -> Any:
    """List advertisement creatives."""
    return j(core.ad_list(category=category, slot=slot, status=status, advertiser=advertiser,
                          tag=tag, limit=limit))


@app.post("/ads", tags=["ads"], status_code=201)
def ad_create(payload: AdCreateRequest) -> Any:
    """Create an advertisement creative."""
    return j(core.ad_create(**payload.model_dump(exclude_none=True)))


@app.get("/ads/{ad_id}", tags=["ads"])
def ad_get(ad_id: str) -> Any:
    """Fetch one advertisement."""
    return j(core.ad_get(ad_id))


@app.put("/ads/{ad_id}", tags=["ads"])
def ad_update(ad_id: str, payload: AdUpdateRequest) -> Any:
    """Update an advertisement."""
    return j(core.ad_update(ad_id, **payload.model_dump(exclude_none=True)))


@app.delete("/ads/{ad_id}", tags=["ads"])
def ad_delete(ad_id: str) -> Any:
    """Delete an advertisement."""
    return j(core.ad_delete(ad_id))


@app.post("/ads/{ad_id}/event", tags=["ads"])
def ad_event(ad_id: str, payload: AdEventRequest, request: Request) -> Any:
    """Report that the app showed (``impression``) or a person tapped (``click``) an ad.

    One viewer counts once per ad per 10 minutes (impressions) / 30 minutes (clicks),
    so refreshes and repeated taps don't bill the advertiser twice."""
    event = payload.event.strip().lower()
    if event not in ads_network.WINDOWS:
        raise HTTPException(status_code=422, detail="event must be 'impression' or 'click'")
    if core.content.find_ad(ad_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown advertisement: {ad_id}")
    viewer, _ = ai_guard._caller(request)
    if not ads_network.first_time(viewer, ad_id, event):
        return {"id": ad_id, "event": event, "counted": False}
    return {**core.content.record_ad_event(ad_id, event=event), "counted": True}


@app.post("/ads/{ad_id}/track", tags=["ads"])
def ad_track(ad_id: str, event: str = "impression", count: int = 1) -> Any:
    """Record an impression / click / spend event."""
    return j(core.ad_track(ad_id, event=event, count=count))


# ==================================================================
# USERS & ROLES (RBAC)
# ==================================================================


class RoleCreateRequest(BaseModel):
    name: str
    label: str
    description: Optional[str] = None
    portal_area: str = "staff"
    level: int = 20
    permissions: Optional[List[str]] = None


class RoleUpdateRequest(BaseModel):
    label: Optional[str] = None
    description: Optional[str] = None
    portal_area: Optional[str] = None
    level: Optional[int] = None
    permissions: Optional[List[str]] = None


class SetRolesRequest(BaseModel):
    roles: List[str]


class AddRoleRequest(BaseModel):
    role: str


class PermissionRequest(BaseModel):
    permission: str


@app.get("/roles/permissions", tags=["roles"])
def roles_permissions() -> Any:
    """The full permission catalogue."""
    return j(core.auth_permissions())


@app.get("/roles/summary", tags=["roles"])
def roles_summary() -> Any:
    """Roles by portal area, permission count and per-role member counts."""
    return j(core.auth_role_summary())


@app.get("/roles", tags=["roles"])
def roles_list(portal_area: Optional[str] = None) -> Any:
    """List portal roles."""
    return j(core.auth_list_roles(portal_area=portal_area))


@app.post("/roles", tags=["roles"], status_code=201)
def roles_create(payload: RoleCreateRequest) -> Any:
    """Create a custom role."""
    return j(core.auth_create_role(**payload.model_dump(exclude_none=True)))


@app.get("/roles/{name}/users", tags=["roles"])
def roles_users(name: str) -> Any:
    """All users holding a given role."""
    return j(core.auth_users_by_role(name))


@app.get("/roles/{name}", tags=["roles"])
def roles_get(name: str) -> Any:
    """Fetch one role with its permissions and member count."""
    return j(core.auth_get_role(name))


@app.put("/roles/{name}", tags=["roles"])
def roles_update(name: str, payload: RoleUpdateRequest) -> Any:
    """Update a role."""
    return j(core.auth_update_role(name, **payload.model_dump(exclude_none=True)))


@app.delete("/roles/{name}", tags=["roles"])
def roles_delete(name: str) -> Any:
    """Delete a custom role."""
    return j(core.auth_delete_role(name))


@app.get("/users/{user_id}/permissions/check", tags=["roles"])
def users_permission_check(user_id: str, permission: str) -> Any:
    """Check whether a user holds a permission."""
    return j(core.auth_check_permission(user_id, permission))


@app.get("/users/{user_id}/permissions", tags=["roles"])
def users_permissions(user_id: str) -> Any:
    """A user's effective roles and permissions."""
    return j(core.auth_user_permissions(user_id=user_id))


@app.post("/users/{user_id}/permissions", tags=["roles"])
def users_grant_permission(user_id: str, payload: PermissionRequest) -> Any:
    """Grant an extra permission directly to a user."""
    return j(core.auth_grant_permission(user_id, payload.permission))


@app.delete("/users/{user_id}/permissions/{permission}", tags=["roles"])
def users_revoke_permission(user_id: str, permission: str) -> Any:
    """Revoke a directly-granted permission."""
    return j(core.auth_revoke_permission(user_id, permission))


@app.get("/users/{user_id}/roles", tags=["roles"])
def users_roles(user_id: str) -> Any:
    """A user's roles and primary role."""
    return j(core.auth_user_roles(user_id=user_id))


@app.put("/users/{user_id}/roles", tags=["roles"])
def users_set_roles(user_id: str, payload: SetRolesRequest) -> Any:
    """Replace a user's whole role set."""
    return j(core.auth_set_user_roles(user_id, payload.roles))


@app.post("/users/{user_id}/roles", tags=["roles"], status_code=201)
def users_assign_role(user_id: str, payload: AddRoleRequest) -> Any:
    """Grant one role to a user."""
    return j(core.auth_assign_role(user_id, payload.role))


@app.delete("/users/{user_id}/roles/{role}", tags=["roles"])
def users_revoke_role(user_id: str, role: str) -> Any:
    """Remove one role from a user."""
    return j(core.auth_revoke_role(user_id, role))


# ==================================================================
# CONSTRUCTION WING
# ==================================================================


class ConstructionEstimateRequest(BaseModel):
    covered_area: float
    floors: int = 1
    building_type: str = "house"
    quality_tier: str = "standard"
    system: str = "rcc_frame"
    city: Optional[str] = None
    plot_area: Optional[float] = None
    escalation_years: float = 0.0


class ConstructionSaveRequest(ConstructionEstimateRequest):
    title: str
    notes: Optional[str] = None


class ConstructionReportRequest(BaseModel):
    covered_area: float
    floors: int = 1
    building_type: str = "house"
    quality_tier: str = "standard"
    system: str = "rcc_frame"
    city: Optional[str] = None


@app.get("/construction/overview", tags=["construction"])
def construction_overview() -> Any:
    """Counts, categories and configuration for the construction wing."""
    return j(core.construction_overview())


@app.get("/construction/techniques", tags=["construction"])
def construction_techniques(category: Optional[str] = None, building_type: Optional[str] = None,
                            max_floors: Optional[int] = None, min_floors: Optional[int] = None) -> Any:
    """Catalogue of construction techniques / systems."""
    return j(core.construction_techniques(category=category, building_type=building_type,
                                          max_floors=max_floors, min_floors=min_floors))


@app.get("/construction/techniques/{key}", tags=["construction"])
def construction_technique(key: str) -> Any:
    """One construction technique by key."""
    return j(core.construction_technique(key))


@app.get("/construction/materials", tags=["construction"])
def construction_materials(category: Optional[str] = None) -> Any:
    """Building-material catalogue with unit rates."""
    return j(core.construction_materials(category=category))


@app.get("/construction/materials/{key}", tags=["construction"])
def construction_material(key: str) -> Any:
    """One building material by key."""
    return j(core.construction_material(key))


@app.get("/construction/element-rates", tags=["construction"])
def construction_element_rates() -> Any:
    """BOQ element unit rates for rate analysis."""
    return j(core.construction_element_rates())


@app.get("/construction/rate-analysis", tags=["construction"])
def construction_rate_analysis(element: str, city: Optional[str] = None) -> Any:
    """Rate analysis for one BOQ element."""
    return j(core.construction_rate_analysis(element, city))


@app.post("/construction/estimate", tags=["construction"])
def construction_estimate(payload: ConstructionEstimateRequest) -> Any:
    """Parameterised construction-cost estimate."""
    return j(core.construction_estimate(**payload.model_dump(exclude_none=True)))


@app.get("/construction/timeline", tags=["construction"])
def construction_timeline(covered_area: float, floors: int = 1, building_type: str = "house",
                          system: str = "rcc_frame") -> Any:
    """Phase-weighted construction timeline."""
    return j(core.construction_timeline(covered_area, floors=floors, building_type=building_type,
                                        system=system))


@app.get("/construction/takeoff", tags=["construction"])
def construction_takeoff(covered_area: float, quality_tier: str = "standard",
                         building_type: str = "house") -> Any:
    """Indicative material take-off."""
    return j(core.construction_takeoff(covered_area, quality_tier=quality_tier, building_type=building_type))


@app.get("/construction/compare", tags=["construction"])
def construction_compare(covered_area: float, floors: int = 1, building_type: str = "house",
                         quality_tier: str = "standard", city: Optional[str] = None,
                         category: str = "structure") -> Any:
    """Compare competing construction techniques."""
    return j(core.construction_compare(covered_area, floors=floors, building_type=building_type,
                                       quality_tier=quality_tier, city=city, category=category))


@app.get("/construction/impact", tags=["construction"])
def construction_impact(covered_area: float, building_type: str = "house", city: Optional[str] = None,
                        from_tier: str = "standard", to_tier: str = "premium",
                        market_rate_sqft: float = 12000.0, gross_yield: float = 0.05,
                        floors: int = 1) -> Any:
    """Impact of construction quality on value, rent and payback."""
    return j(core.construction_impact(covered_area, building_type=building_type, city=city,
                                      from_tier=from_tier, to_tier=to_tier,
                                      market_rate_sqft=market_rate_sqft, gross_yield=gross_yield,
                                      floors=floors))


@app.get("/construction/advisory", tags=["construction"])
def construction_advisory(plot_area: float, floors: int = 2, building_type: str = "house",
                          city: Optional[str] = None, soil: str = "sandy_loam",
                          seismic_zone: str = "2A", budget_per_sqft: Optional[float] = None) -> Any:
    """Recommend a technique, foundation and guidelines for a site."""
    return j(core.construction_advisory(plot_area, floors=floors, building_type=building_type, city=city,
                                        soil=soil, seismic_zone=seismic_zone,
                                        budget_per_sqft=budget_per_sqft))


@app.get("/construction/guidelines", tags=["construction"])
def construction_guidelines(category: Optional[str] = None, authority: Optional[str] = None,
                            building_type: Optional[str] = None) -> Any:
    """Building codes, byelaws and guidelines."""
    return j(core.construction_guidelines(category=category, authority=authority,
                                          building_type=building_type))


@app.get("/construction/approvals", tags=["construction"])
def construction_approvals(project_type: str = "house", city: Optional[str] = None) -> Any:
    """NOC / approval workflow for a project type."""
    return j(core.construction_approvals(project_type=project_type, city=city))


@app.get("/construction/qa", tags=["construction"])
def construction_qa(stage: Optional[str] = None) -> Any:
    """QA inspection checklists by stage."""
    return j(core.construction_qa(stage))


@app.get("/construction/hse", tags=["construction"])
def construction_hse() -> Any:
    """Health, safety & environment rules."""
    return j(core.construction_hse())


@app.get("/construction/trades", tags=["construction"])
def construction_trades() -> Any:
    """Construction trades with daily wage rates."""
    return j(core.construction_trades())


@app.post("/construction/estimates", tags=["construction"], status_code=201)
def construction_estimate_save(payload: ConstructionSaveRequest) -> Any:
    """Compute and persist a construction estimate."""
    return j(core.construction_estimate_save(**payload.model_dump(exclude_none=True)))


@app.get("/construction/estimates", tags=["construction"])
def construction_estimates(building_type: Optional[str] = None, city: Optional[str] = None) -> Any:
    """Saved construction estimates."""
    return j(core.construction_estimates(building_type=building_type, city=city))


@app.get("/construction/estimates/{estimate_id}", tags=["construction"])
def construction_estimate_get(estimate_id: str) -> Any:
    """One saved construction estimate."""
    return j(core.construction_estimate_get(estimate_id))


@app.get("/construction/portal", tags=["construction"], response_class=HTMLResponse)
def construction_portal(lang: str = Depends(ui_lang), theme: str = Depends(ui_theme)) -> HTMLResponse:
    """The Construction wing page (HTML)."""
    return HTMLResponse(content=core.construction_portal(lang=lang, theme=theme))


@app.get("/construction/portal.html", tags=["construction"], response_class=HTMLResponse)
def construction_portal_html(lang: str = Depends(ui_lang), theme: str = Depends(ui_theme)) -> HTMLResponse:
    """Alias of ``/construction/portal`` that always serves HTML."""
    return HTMLResponse(content=core.construction_portal(lang=lang, theme=theme))


@app.post("/construction/report", tags=["construction"], response_class=HTMLResponse)
def construction_report(payload: ConstructionReportRequest, lang: str = Depends(ui_lang),
                        theme: str = Depends(ui_theme)) -> HTMLResponse:
    """Construction cost report (HTML)."""
    return HTMLResponse(content=core.construction_report(**payload.model_dump(exclude_none=True),
                                                         lang=lang, theme=theme))


# ==================================================================
# MAINTENANCE WING
# ==================================================================


class MaintenanceEstimateRequest(BaseModel):
    covered_area: float
    property_type: str = "house"
    tier: str = "standard"
    quality: str = "standard"
    age_years: float = 0.0
    city: Optional[str] = None
    floors: int = 1


class MaintenancePlanRequest(BaseModel):
    covered_area: float
    property_type: str = "house"
    tier: str = "standard"
    quality: str = "standard"
    age_years: float = 0.0
    city: Optional[str] = None
    title: str
    notes: Optional[str] = None


class MaintenanceReportRequest(BaseModel):
    covered_area: float
    property_type: str = "house"
    tier: str = "standard"
    quality: str = "standard"
    age_years: float = 0.0
    city: Optional[str] = None


class WorkOrderCreateRequest(BaseModel):
    title: str
    property_type: str = "house"
    component: Optional[str] = None
    defect: Optional[str] = None
    priority: str = "routine"
    description: Optional[str] = None
    estimated_cost: float = 0.0
    assignee: Optional[str] = None


class WorkOrderUpdateRequest(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None
    assignee: Optional[str] = None
    estimated_cost: Optional[float] = None
    description: Optional[str] = None


@app.get("/maintenance/overview", tags=["maintenance"])
def maintenance_overview() -> Any:
    """Counts, categories and configuration for the maintenance wing."""
    return j(core.maintenance_overview())


@app.get("/maintenance/components", tags=["maintenance"])
def maintenance_components(category: Optional[str] = None) -> Any:
    """Maintainable components with service lives and criticality."""
    return j(core.maintenance_components(category=category))


@app.get("/maintenance/components/{key}", tags=["maintenance"])
def maintenance_component(key: str) -> Any:
    """One maintainable component by key."""
    return j(core.maintenance_component(key))


@app.get("/maintenance/services", tags=["maintenance"])
def maintenance_services(category: Optional[str] = None, emergency: Optional[bool] = None) -> Any:
    """Maintenance services and trades with cost bands."""
    return j(core.maintenance_services(category=category, emergency=emergency))


@app.get("/maintenance/services/{key}", tags=["maintenance"])
def maintenance_service(key: str) -> Any:
    """One maintenance service by key."""
    return j(core.maintenance_service(key))


@app.get("/maintenance/defects", tags=["maintenance"])
def maintenance_defects(category: Optional[str] = None, severity: Optional[str] = None,
                        component: Optional[str] = None) -> Any:
    """The defect catalogue."""
    return j(core.maintenance_defects(category=category, severity=severity, component=component))


@app.get("/maintenance/defects/{key}", tags=["maintenance"])
def maintenance_defect(key: str) -> Any:
    """One defect by key."""
    return j(core.maintenance_defect(key))


@app.get("/maintenance/estimate", tags=["maintenance"])
def maintenance_estimate(covered_area: float, property_type: str = "house", tier: str = "standard",
                         quality: str = "standard", age_years: float = 0.0, city: Optional[str] = None,
                         floors: int = 1) -> Any:
    """Annual maintenance cost estimate with a category breakdown and reserve."""
    return j(core.maintenance_estimate(covered_area, property_type=property_type, tier=tier,
                                      quality=quality, age_years=age_years, city=city, floors=floors))


@app.get("/maintenance/schedule", tags=["maintenance"])
def maintenance_schedule(property_type: str = "house", age_years: float = 0.0,
                         horizon_months: int = 12) -> Any:
    """A periodic preventive-maintenance calendar."""
    return j(core.maintenance_schedule(property_type=property_type, age_years=age_years,
                                       horizon_months=horizon_months))


@app.get("/maintenance/lifecycle", tags=["maintenance"])
def maintenance_lifecycle(covered_area: float, property_type: str = "house",
                          quality: str = "standard", age_years: float = 0.0,
                          city: Optional[str] = None, years: int = 30) -> Any:
    """Multi-year capital-replacement schedule (reserve study)."""
    return j(core.maintenance_lifecycle(covered_area, property_type=property_type, quality=quality,
                                        age_years=age_years, city=city, years=years))


@app.get("/maintenance/reserve", tags=["maintenance"])
def maintenance_reserve(covered_area: float, property_type: str = "house", quality: str = "standard",
                        age_years: float = 0.0, city: Optional[str] = None) -> Any:
    """Annual sinking-fund (reserve) contribution."""
    return j(core.maintenance_reserve(covered_area, property_type=property_type, quality=quality,
                                      age_years=age_years, city=city))


@app.get("/maintenance/condition", tags=["maintenance"])
def maintenance_condition(age_years: float, property_type: str = "house",
                          ratings: Optional[str] = None) -> Any:
    """Score a building's condition into a band with recommended actions."""
    parsed: Optional[Dict[str, int]] = json.loads(ratings) if ratings else None
    return j(core.maintenance_condition(age_years, property_type=property_type, ratings=parsed))


@app.get("/maintenance/repair-estimate", tags=["maintenance"])
def maintenance_repair_estimate(defect: str, quantity: float = 1.0, city: Optional[str] = None) -> Any:
    """Estimate the cost to repair a known defect."""
    return j(core.maintenance_repair_estimate(defect, quantity=quantity, city=city))


@app.get("/maintenance/repair-or-replace", tags=["maintenance"])
def maintenance_repair_or_replace(component: str, age_years: float, condition: Optional[str] = None,
                                  covered_area: float = 1000.0, quality: str = "standard",
                                  city: Optional[str] = None) -> Any:
    """Repair-vs-replace decision with a 5-year cost comparison."""
    return j(core.maintenance_repair_or_replace(component, age_years, condition=condition,
                                                covered_area=covered_area, quality=quality, city=city))


@app.get("/maintenance/impact", tags=["maintenance"])
def maintenance_impact(market_value: float, monthly_rent: float, covered_area: float = 1000.0,
                       current_condition: str = "fair", tier: str = "standard") -> Any:
    """How maintenance moves value, rent, yield and occupancy."""
    return j(core.maintenance_impact(market_value, monthly_rent, covered_area, current_condition, tier))


@app.get("/maintenance/guidelines", tags=["maintenance"])
def maintenance_guidelines(category: Optional[str] = None) -> Any:
    """Maintenance best-practice, compliance and safety guidelines."""
    return j(core.maintenance_guidelines(category=category))


@app.get("/maintenance/warranty", tags=["maintenance"])
def maintenance_warranty(component: Optional[str] = None) -> Any:
    """Warranty terms by component."""
    return j(core.maintenance_warranty(component))


@app.get("/maintenance/inspection", tags=["maintenance"])
def maintenance_inspection(area: Optional[str] = None) -> Any:
    """Inspection checklists by area."""
    return j(core.maintenance_inspection(area))


@app.post("/maintenance/plans", tags=["maintenance"], status_code=201)
def maintenance_plan_save(payload: MaintenancePlanRequest) -> Any:
    """Compute and persist a maintenance plan."""
    return j(core.maintenance_plan_save(**payload.model_dump(exclude_none=True)))


@app.get("/maintenance/plans", tags=["maintenance"])
def maintenance_plans(property_type: Optional[str] = None) -> Any:
    """Saved maintenance plans."""
    return j(core.maintenance_plans(property_type=property_type))


@app.get("/maintenance/plans/{plan_id}", tags=["maintenance"])
def maintenance_plan_get(plan_id: str) -> Any:
    """One saved maintenance plan."""
    return j(core.maintenance_plan_get(plan_id))


@app.post("/maintenance/work-orders", tags=["maintenance"], status_code=201)
def maintenance_work_order_create(payload: WorkOrderCreateRequest) -> Any:
    """Raise a maintenance work order."""
    return j(core.maintenance_work_order_create(**payload.model_dump(exclude_none=True)))


@app.get("/maintenance/work-orders", tags=["maintenance"])
def maintenance_work_orders(status: Optional[str] = None, priority: Optional[str] = None,
                            component: Optional[str] = None) -> Any:
    """List maintenance work orders."""
    return j(core.maintenance_work_orders(status=status, priority=priority, component=component))


@app.get("/maintenance/work-orders/{wo_id}", tags=["maintenance"])
def maintenance_work_order_get(wo_id: str) -> Any:
    """One maintenance work order."""
    return j(core.maintenance_work_order_get(wo_id))


@app.put("/maintenance/work-orders/{wo_id}", tags=["maintenance"])
def maintenance_work_order_update(wo_id: str, payload: WorkOrderUpdateRequest) -> Any:
    """Update a maintenance work order."""
    return j(core.maintenance_work_order_update(wo_id, **payload.model_dump(exclude_none=True)))


@app.get("/maintenance/portal", tags=["maintenance"], response_class=HTMLResponse)
def maintenance_portal(lang: str = Depends(ui_lang), theme: str = Depends(ui_theme)) -> HTMLResponse:
    """The Maintenance wing page (HTML)."""
    return HTMLResponse(content=core.maintenance_portal(lang=lang, theme=theme))


@app.get("/maintenance/portal.html", tags=["maintenance"], response_class=HTMLResponse)
def maintenance_portal_html(lang: str = Depends(ui_lang), theme: str = Depends(ui_theme)) -> HTMLResponse:
    """Alias of ``/maintenance/portal`` that always serves HTML."""
    return HTMLResponse(content=core.maintenance_portal(lang=lang, theme=theme))


@app.post("/maintenance/report", tags=["maintenance"], response_class=HTMLResponse)
def maintenance_report(payload: MaintenanceReportRequest, lang: str = Depends(ui_lang),
                       theme: str = Depends(ui_theme)) -> HTMLResponse:
    """Maintenance report (HTML)."""
    return HTMLResponse(content=core.maintenance_report(**payload.model_dump(exclude_none=True),
                                                        lang=lang, theme=theme))


# ==================================================================
# AGENTIC OS (product agents, runs, smart actions)
# ==================================================================


class AgentPlanRequest(BaseModel):
    agent_key: str
    objective: str = ""
    subject_type: Optional[str] = None
    subject_id: Optional[str] = None


class AgentRunRequest(AgentPlanRequest):
    text: Optional[str] = None
    approve: bool = False
    extra: Optional[Dict[str, Any]] = None


class AgentOrchestrateRequest(BaseModel):
    objective: str
    agents_csv: str


@app.get("/agents/overview", tags=["agents"])
def agents_overview() -> Any:
    """Counts, products, autonomy mix and run activity across the Agentic OS."""
    return j(core.agents_overview())


@app.get("/agents/catalog", tags=["agents"])
def agents_catalog(category: Optional[str] = None, product: Optional[str] = None,
                   priority: Optional[str] = None, autonomy: Optional[str] = None) -> Any:
    """The agent catalogue (product agents plus specialist sub-agents)."""
    return j(core.agents_catalog(category=category, product=product, priority=priority,
                                 autonomy=autonomy))


@app.get("/agents/products", tags=["agents"])
def agent_products(priority: Optional[str] = None) -> Any:
    """The eight roadmap products and their agent modules."""
    return j(core.agent_products(priority=priority))


@app.get("/agents/runs", tags=["agents"])
def agent_runs(agent_key: Optional[str] = None, status: Optional[str] = None) -> Any:
    """Recorded agent runs (the audit trail)."""
    return j(core.agent_runs(agent_key=agent_key, status=status))


@app.get("/agents/runs/{run_id}", tags=["agents"])
def agent_run_get(run_id: str) -> Any:
    """One agent run with its steps, outputs and approvals."""
    return j(core.agent_run_get(run_id))


@app.get("/agents/smart-actions", tags=["agents"])
def agent_smart_actions(limit: int = 15) -> Any:
    """The prioritised Smart Actions morning brief."""
    return j(core.agent_smart_actions(limit=limit))


@app.get("/agents/move-likelihood/{lead_id}", tags=["agents"])
def agent_move_likelihood(lead_id: str) -> Any:
    """Score a CRM lead's likelihood of moving (0–100)."""
    return j(core.agent_move_likelihood(lead_id))


@app.get("/agents/seller-intent", tags=["agents"])
def agent_seller_intent(equity_pct: float = 0.0, holding_years: float = 0.0,
                        market_heat: float = 0.5, life_event: Optional[str] = None,
                        fsbo_signal: bool = False, engagement_score: int = 40) -> Any:
    """Score how likely a contact is to sell (0–100)."""
    return j(core.agent_seller_intent(equity_pct=equity_pct, holding_years=holding_years,
                                      market_heat=market_heat, life_event=life_event,
                                      fsbo_signal=fsbo_signal, engagement_score=engagement_score))


@app.post("/agents/plan", tags=["agents"])
def agent_plan(payload: AgentPlanRequest) -> Any:
    """Plan (but do not execute) an agent run."""
    return j(core.agent_plan(**payload.model_dump(exclude_none=True)))


@app.post("/agents/run", tags=["agents"])
def agent_run(payload: AgentRunRequest) -> Any:
    """Execute an agent run against the live portal."""
    return j(core.agent_run(**payload.model_dump(exclude_none=True)))


@app.post("/agents/runs/{run_id}/approve", tags=["agents"])
def agent_approve(run_id: str, approver: str = "user", execute: bool = True) -> Any:
    """Approve a paused agent run (human-in-the-loop gate)."""
    return j(core.agent_approve(run_id, approver=approver, execute=execute))


@app.post("/agents/orchestrate", tags=["agents"])
def agent_orchestrate(payload: AgentOrchestrateRequest) -> Any:
    """Plan a multi-agent hand-off chain for a shared objective."""
    return j(core.agent_orchestrate(payload.objective, payload.agents_csv))


@app.get("/agents/portal", tags=["agents"], response_class=HTMLResponse)
def agentic_portal(lang: str = Depends(ui_lang), theme: str = Depends(ui_theme)) -> HTMLResponse:
    """The Agentic OS page (HTML)."""
    return HTMLResponse(content=core.agentic_portal(lang=lang, theme=theme))


@app.get("/agents/portal.html", tags=["agents"], response_class=HTMLResponse)
def agentic_portal_html(lang: str = Depends(ui_lang), theme: str = Depends(ui_theme)) -> HTMLResponse:
    """Alias of ``/agents/portal`` that always serves HTML."""
    return HTMLResponse(content=core.agentic_portal(lang=lang, theme=theme))


@app.get("/agents/{key}", tags=["agents"])
def agent_get(key: str) -> Any:
    """One agent's full definition by key."""
    return j(core.agent_get(key))


# ==================================================================
# TRANSACTIONS
# ==================================================================


class TransactionCreateRequest(BaseModel):
    transaction_type: str = "sale"
    price: float = 0.0
    property_id: Optional[str] = None
    property_title: Optional[str] = None
    buyer_name: Optional[str] = None
    seller_name: Optional[str] = None
    listing_agent_id: Optional[str] = None
    selling_agent_id: Optional[str] = None
    commission_rate: Optional[float] = None
    start_date: Optional[str] = None
    notes: Optional[str] = None


class TransactionUpdateRequest(BaseModel):
    stage: Optional[str] = None
    status: Optional[str] = None
    price: Optional[float] = None
    commission_rate: Optional[float] = None
    buyer_name: Optional[str] = None
    seller_name: Optional[str] = None
    notes: Optional[str] = None


class MilestoneRequest(BaseModel):
    key: str
    name: str
    due_date: Optional[str] = None
    owner: str = "broker"
    blocking: bool = False


class MilestoneCompleteRequest(BaseModel):
    as_of: Optional[str] = None


class TermsExtractRequest(BaseModel):
    text: str


class OfferRequest(BaseModel):
    price: float
    buyer_name: Optional[str] = None
    terms: Optional[str] = None


class OfferRespondRequest(BaseModel):
    action: str
    counter_price: Optional[float] = None


class SignatureRequest(BaseModel):
    signer: str
    role: str = "buyer"
    method: str = "esign"
    signed: bool = False


class TransactionCloseRequest(BaseModel):
    commission_rate: Optional[float] = None
    platform_share: float = 0.20
    listing_agent_share: float = 0.40
    selling_agent_share: float = 0.40
    post_to_ledger: bool = True
    record_payouts: bool = True


@app.get("/transactions/stages", tags=["transactions"])
def transaction_stages() -> Any:
    """The transaction lifecycle stages and configuration."""
    return j(core.transaction_stages())


@app.get("/transactions/deadlines", tags=["transactions"])
def transaction_deadlines(horizon_days: int = 14) -> Any:
    """Every transaction milestone due within the horizon."""
    return j(core.transaction_deadlines(horizon_days=horizon_days))


@app.post("/transactions/terms/extract", tags=["transactions"])
def transaction_extract_terms(payload: TermsExtractRequest) -> Any:
    """Extract key contract terms from agreement text."""
    return j(core.transaction_extract_terms(payload.text))


@app.post("/transactions", tags=["transactions"], status_code=201)
def transaction_create(payload: TransactionCreateRequest) -> Any:
    """Open a transaction with its milestone/deadline checklist."""
    return j(core.transaction_create(**payload.model_dump(exclude_none=True)))


@app.get("/transactions", tags=["transactions"])
def transactions_list(status: Optional[str] = None, stage: Optional[str] = None,
                      transaction_type: Optional[str] = None) -> Any:
    """List transactions."""
    return j(core.transactions_list(status=status, stage=stage, transaction_type=transaction_type))


@app.get("/transactions/{tx_id}", tags=["transactions"])
def transaction_get(tx_id: str) -> Any:
    """One transaction with milestones, terms and offers."""
    return j(core.transaction_get(tx_id))


@app.put("/transactions/{tx_id}", tags=["transactions"])
def transaction_update(tx_id: str, payload: TransactionUpdateRequest) -> Any:
    """Update a transaction's stage, price, parties or commission rate."""
    return j(core.transaction_update(tx_id, **payload.model_dump(exclude_none=True)))


@app.get("/transactions/{tx_id}/progress", tags=["transactions"])
def transaction_progress(tx_id: str) -> Any:
    """Completion %, overdue milestones and next deadline."""
    return j(core.transaction_progress(tx_id))


@app.get("/transactions/{tx_id}/signatures", tags=["transactions"])
def transaction_signatures(tx_id: str) -> Any:
    """E-signature status for a transaction."""
    return j(core.transaction_signatures(tx_id))


@app.post("/transactions/{tx_id}/signatures", tags=["transactions"], status_code=201)
def transaction_signature_add(tx_id: str, payload: SignatureRequest) -> Any:
    """Record an e-signature request / signing."""
    return j(core.transaction_signature_add(tx_id, **payload.model_dump(exclude_none=True)))


@app.post("/transactions/{tx_id}/milestones", tags=["transactions"], status_code=201)
def transaction_milestone_add(tx_id: str, payload: MilestoneRequest) -> Any:
    """Add a custom milestone/deadline."""
    return j(core.transaction_milestone_add(tx_id, **payload.model_dump(exclude_none=True)))


@app.post("/transactions/{tx_id}/milestones/{key}/complete", tags=["transactions"])
def transaction_milestone_complete(tx_id: str, key: str,
                                   payload: Optional[MilestoneCompleteRequest] = None) -> Any:
    """Mark a milestone complete."""
    body = payload.model_dump(exclude_none=True) if payload else {}
    return j(core.transaction_milestone_complete(tx_id, key, **body))


@app.post("/transactions/{tx_id}/offers", tags=["transactions"], status_code=201)
def transaction_offer_add(tx_id: str, payload: OfferRequest) -> Any:
    """Record an offer on a transaction."""
    return j(core.transaction_offer_add(tx_id, **payload.model_dump(exclude_none=True)))


@app.post("/transactions/offers/{offer_id}/respond", tags=["transactions"])
def transaction_offer_respond(offer_id: str, payload: OfferRespondRequest) -> Any:
    """Respond to an offer (counter / accept / reject / withdraw)."""
    return j(core.transaction_offer_respond(offer_id, **payload.model_dump(exclude_none=True)))


@app.post("/transactions/{tx_id}/close", tags=["transactions"])
def transaction_close(tx_id: str, payload: TransactionCloseRequest) -> Any:
    """Close a transaction: commission, VAT, revenue share, ledger and payouts."""
    return j(core.transaction_close(tx_id, **payload.model_dump(exclude_none=True)))


@app.post("/transactions/{tx_id}/report", tags=["transactions"], response_class=HTMLResponse)
def transaction_report(tx_id: str, lang: str = Depends(ui_lang),
                       theme: str = Depends(ui_theme)) -> HTMLResponse:
    """Printable transaction/closing report (HTML)."""
    return HTMLResponse(content=core.transaction_report(tx_id, lang=lang, theme=theme))


# ==================================================================
# INTELLIGENCE: buyer / seller / investment
# ==================================================================


class BuyerParseRequest(BaseModel):
    text: str


class BuyerRecommendRequest(BaseModel):
    text: Optional[str] = None
    limit: int = 8
    city: Optional[str] = None
    category: Optional[str] = None
    use_type: Optional[str] = None
    max_price: Optional[float] = None


class BuyerReportRequest(BaseModel):
    text: str


class UnderwriteRequest(BaseModel):
    purchase_price: float
    monthly_rent: float = 0.0
    annual_rent: Optional[float] = None
    down_payment_share: float = 0.25
    loan_rate: Optional[float] = None
    loan_years: int = 20
    vacancy_rate: float = 0.05
    operating_expense_rate: float = 0.30
    appreciation_rate: float = 0.06
    exit_cap_rate: float = 0.07
    hold_years: int = 10
    tax_rate: float = 0.0


class PortfolioAlertsRequest(BaseModel):
    holdings: Optional[List[Dict[str, Any]]] = None
    interest_rate: float = 0.18
    rent_index_change: float = 0.0
    supply_change: float = 0.0
    market_heat: float = 0.5


class InvestmentReportRequest(BaseModel):
    city: Optional[str] = None
    rental_yield: float = 0.045
    min_cap_rate: float = 0.025


@app.post("/intelligence/buyer/parse", tags=["intelligence"])
def buyer_parse_requirement(payload: BuyerParseRequest) -> Any:
    """Parse a natural-language buyer brief into a structured requirement."""
    return j(core.buyer_parse_requirement(payload.text))


@app.post("/intelligence/buyer/recommend", tags=["intelligence"])
def buyer_recommend(payload: BuyerRecommendRequest) -> Any:
    """Rank live listings against a parsed buyer brief."""
    return j(core.buyer_recommend(**payload.model_dump(exclude_none=True)))


@app.get("/intelligence/buyer/anomalies", tags=["intelligence"])
def buyer_anomaly_scan(city: Optional[str] = None, category: Optional[str] = None,
                       use_type: Optional[str] = None, threshold: float = 1.0) -> Any:
    """Z-score the market for bargains and overpriced listings."""
    return j(core.buyer_anomaly_scan(city=city, category=category, use_type=use_type,
                                     threshold=threshold))


@app.get("/intelligence/buyer/affordability", tags=["intelligence"])
def buyer_affordability(price: float, down_payment_share: float = 0.25,
                        annual_rate: Optional[float] = None, years: Optional[int] = None,
                        monthly_income: Optional[float] = None, property_tax_rate: float = 0.01,
                        holding_monthly: float = 0.0, other_debt_monthly: float = 0.0) -> Any:
    """Monthly payment, tax, holding costs and an affordability verdict."""
    return j(core.buyer_affordability(price, down_payment_share=down_payment_share,
                                      annual_rate=annual_rate, years=years,
                                      monthly_income=monthly_income, property_tax_rate=property_tax_rate,
                                      holding_monthly=holding_monthly,
                                      other_debt_monthly=other_debt_monthly))


@app.post("/intelligence/buyer/report", tags=["intelligence"], response_class=HTMLResponse)
def buyer_report(payload: BuyerReportRequest, lang: str = Depends(ui_lang),
                 theme: str = Depends(ui_theme)) -> HTMLResponse:
    """The buyer brief & shortlist (HTML)."""
    return HTMLResponse(content=core.buyer_report(payload.text, lang=lang, theme=theme))


@app.get("/intelligence/seller/cma/{property_id}", tags=["intelligence"])
def seller_cma(property_id: str, comp_ids: Optional[str] = None) -> Any:
    """Adjusted-comparable market analysis for a property."""
    comps = [c.strip() for c in comp_ids.split(",") if c.strip()] if comp_ids else None
    return j(core.seller_cma(property_id, comps))


@app.get("/intelligence/seller/net-proceeds", tags=["intelligence"])
def seller_net_proceeds(price: float, commission_rate: float = 0.02, other_cost_rate: float = 0.01,
                        mortgage_payoff: float = 0.0, cost_basis: Optional[float] = None,
                        capital_gains_rate: Optional[float] = None) -> Any:
    """A seller's net cash after commission, costs, payoff and capital gains."""
    return j(core.seller_net_proceeds(price, commission_rate=commission_rate,
                                      other_cost_rate=other_cost_rate,
                                      mortgage_payoff=mortgage_payoff, cost_basis=cost_basis,
                                      capital_gains_rate=capital_gains_rate))


@app.get("/intelligence/seller/marketing/{property_id}", tags=["intelligence"])
def seller_marketing_assets(property_id: str, tone: str = "professional",
                            lang: str = "en") -> Any:
    """Generate a full marketing kit for a listing."""
    return j(core.seller_marketing_assets(property_id, tone=tone, lang=lang))


@app.post("/intelligence/seller/report/{property_id}", tags=["intelligence"],
          response_class=HTMLResponse)
def seller_report(property_id: str, lang: str = Depends(ui_lang),
                  theme: str = Depends(ui_theme)) -> HTMLResponse:
    """Seller pricing & marketing report (HTML)."""
    return HTMLResponse(content=core.seller_report(property_id, lang=lang, theme=theme))


@app.post("/intelligence/investment/underwrite", tags=["intelligence"])
def investment_underwrite(payload: UnderwriteRequest) -> Any:
    """Underwrite a deal: returns, debt, DSCR and a risk-adjusted grade."""
    return j(core.investment_underwrite(**payload.model_dump(exclude_none=True)))


@app.get("/intelligence/investment/screen", tags=["intelligence"])
def investment_screen(city: Optional[str] = None, category: Optional[str] = None,
                      rental_yield: float = 0.045, min_cap_rate: Optional[float] = None,
                      min_dscr: Optional[float] = None, max_price: Optional[float] = None,
                      down_payment_share: float = 0.25, loan_rate: float = 0.16,
                      loan_years: int = 20, hold_years: int = 10, limit: int = 10) -> Any:
    """Screen the live listing book into a risk-adjusted shortlist."""
    return j(core.investment_screen(city=city, category=category, rental_yield=rental_yield,
                                    min_cap_rate=min_cap_rate, min_dscr=min_dscr,
                                    max_price=max_price, down_payment_share=down_payment_share,
                                    loan_rate=loan_rate, loan_years=loan_years,
                                    hold_years=hold_years, limit=limit))


@app.post("/intelligence/investment/alerts", tags=["intelligence"])
def investment_portfolio_alerts(payload: PortfolioAlertsRequest) -> Any:
    """Proactive investor alerts for a portfolio."""
    return j(core.investment_portfolio_alerts(**payload.model_dump(exclude_none=True)))


@app.post("/intelligence/investment/report", tags=["intelligence"], response_class=HTMLResponse)
def investment_report(payload: InvestmentReportRequest, lang: str = Depends(ui_lang),
                      theme: str = Depends(ui_theme)) -> HTMLResponse:
    """Investment screener report (HTML)."""
    return HTMLResponse(content=core.investment_report(**payload.model_dump(exclude_none=True),
                                                       lang=lang, theme=theme))


# ==================================================================
# AUTONOMOUS LEASING
# ==================================================================


class RentalUnitCreateRequest(BaseModel):
    title: str
    rent: float = 0.0
    city: Optional[str] = None
    scheme: Optional[str] = None
    bedrooms: Optional[int] = None
    area: Optional[float] = None
    deposit: float = 0.0
    monthly_holding_cost: float = 0.0
    amenities: Optional[List[str]] = None


class LeasingInquiryRequest(BaseModel):
    message: str
    unit_id: Optional[str] = None
    channel: str = "web_chat"
    lang: str = "en"


class LeasingApplicationRequest(BaseModel):
    applicant: str
    monthly_income: float
    unit_id: Optional[str] = None
    employment: str = "salaried"
    references_count: int = 0
    credit_proxy: int = 70
    occupants: int = 1
    pets: bool = False
    move_in_days: int = 15


@app.get("/leasing/units", tags=["leasing"])
def leasing_units(status: Optional[str] = None, city: Optional[str] = None,
                  limit: int = 50) -> Any:
    """Rental units available to the leasing agent."""
    return j(core.leasing_units(status=status, city=city, limit=limit))


@app.get("/leasing/rent-floor", tags=["leasing"])
def leasing_rent_floor(monthly_holding_cost: float, margin: Optional[float] = None) -> Any:
    """Minimum rent that keeps a unit cash-flow positive."""
    return j(core.leasing_rent_floor(monthly_holding_cost, margin=margin))


@app.get("/leasing/units/{unit_id}", tags=["leasing"])
def leasing_unit(unit_id: str) -> Any:
    """One rental unit by id."""
    return j(core.leasing_unit(unit_id))


@app.post("/leasing/units", tags=["leasing"], status_code=201)
def leasing_unit_create(payload: RentalUnitCreateRequest) -> Any:
    """Register a rental unit."""
    return j(core.leasing_unit_create(**payload.model_dump(exclude_none=True)))


@app.post("/leasing/inquiries", tags=["leasing"], status_code=201)
def leasing_inquiry(payload: LeasingInquiryRequest) -> Any:
    """Handle a tenant inquiry autonomously."""
    return j(core.leasing_inquiry(**payload.model_dump(exclude_none=True)))


@app.get("/leasing/inquiries", tags=["leasing"])
def leasing_inquiries(unit_id: Optional[str] = None, intent: Optional[str] = None) -> Any:
    """Log of handled leasing inquiries."""
    return j(core.leasing_inquiries(unit_id=unit_id, intent=intent))


@app.post("/leasing/apply", tags=["leasing"], status_code=201)
def leasing_screen_application(payload: LeasingApplicationRequest) -> Any:
    """Screen a rental application."""
    return j(core.leasing_screen_application(**payload.model_dump(exclude_none=True)))


@app.get("/leasing/renewals", tags=["leasing"])
def leasing_renewals(uplift: float = 0.08, hold_rent_if_risky: bool = True) -> Any:
    """Renewal recommendations for every active lease."""
    return j(core.leasing_renewals(uplift=uplift, hold_rent_if_risky=hold_rent_if_risky))


@app.get("/leasing/collection", tags=["leasing"])
def leasing_collection() -> Any:
    """Rent-collection board from the ledger."""
    return j(core.leasing_collection())


@app.get("/leasing/funnel", tags=["leasing"])
def leasing_funnel() -> Any:
    """Leasing funnel metrics."""
    return j(core.leasing_funnel())


@app.get("/leasing/portal", tags=["leasing"], response_class=HTMLResponse)
def leasing_portal(lang: str = Depends(ui_lang), theme: str = Depends(ui_theme)) -> HTMLResponse:
    """The Autonomous Leasing wing page (HTML)."""
    return HTMLResponse(content=core.leasing_portal(lang=lang, theme=theme))


@app.get("/leasing/portal.html", tags=["leasing"], response_class=HTMLResponse)
def leasing_portal_html(lang: str = Depends(ui_lang), theme: str = Depends(ui_theme)) -> HTMLResponse:
    """Alias of ``/leasing/portal`` that always serves HTML."""
    return HTMLResponse(content=core.leasing_portal(lang=lang, theme=theme))


# ==================================================================
# AI MARKETING CONDUCTOR
# ==================================================================


class RouteAddRequest(BaseModel):
    name: str
    match: Dict[str, Any]
    assign_to_agent_id: Optional[str] = None
    queue: str = "general"
    priority: int = 100
    sla_hours: int = 4


class ContentGenerateRequest(BaseModel):
    kind: str = "market_report"
    property_id: Optional[str] = None
    tone: str = "professional"
    lang: str = "en"
    topic: Optional[str] = None


class CampaignRequest(BaseModel):
    objective: str
    budget: float
    channels: List[str]
    days: int = 14
    audience: Optional[int] = None


class ApproveRequest(BaseModel):
    approver: str = "user"


@app.get("/marketing/channels", tags=["marketing"])
def marketing_channels() -> Any:
    """Cross-channel lead sources and content kinds."""
    return j(core.marketing_channels())


@app.get("/marketing/routes", tags=["marketing"])
def marketing_routes() -> Any:
    """Lead-routing rules."""
    return j(core.marketing_routes())


@app.post("/marketing/routes", tags=["marketing"], status_code=201)
def marketing_route_add(payload: RouteAddRequest) -> Any:
    """Add a lead-routing rule."""
    return j(core.marketing_route_add(**payload.model_dump(exclude_none=True)))


@app.post("/marketing/qualify/{lead_id}", tags=["marketing"])
def marketing_qualify(lead_id: str) -> Any:
    """Qualify a CRM lead and sync the score back."""
    return j(core.marketing_qualify(lead_id))


@app.post("/marketing/route/{lead_id}", tags=["marketing"])
def marketing_route_lead(lead_id: str) -> Any:
    """Route a CRM lead to the best-matching rule."""
    return j(core.marketing_route_lead(lead_id))


@app.get("/marketing/reengagement", tags=["marketing"])
def marketing_reengagement(inactive_days: Optional[int] = None,
                           min_score: Optional[int] = None) -> Any:
    """Dormant / false-negative lead re-engagement candidates."""
    return j(core.marketing_reengagement(inactive_days=inactive_days, min_score=min_score))


@app.post("/marketing/content", tags=["marketing"], status_code=201)
def marketing_generate_content(payload: ContentGenerateRequest) -> Any:
    """Generate a marketing content asset."""
    return j(core.marketing_generate_content(**payload.model_dump(exclude_none=True)))


@app.get("/marketing/content", tags=["marketing"])
def marketing_content_assets(status: Optional[str] = None) -> Any:
    """Content assets by status."""
    return j(core.marketing_content_assets(status=status))


@app.post("/marketing/content/{asset_id}/approve", tags=["marketing"])
def marketing_content_approve(asset_id: str, payload: Optional[ApproveRequest] = None) -> Any:
    """Human approval gate for a content asset."""
    body = payload.model_dump(exclude_none=True) if payload else {}
    return j(core.marketing_content_approve(asset_id, **body))


@app.post("/marketing/campaigns", tags=["marketing"], status_code=201)
def marketing_campaign_plan(payload: CampaignRequest) -> Any:
    """Plan a multichannel campaign."""
    return j(core.marketing_campaign_plan(**payload.model_dump(exclude_none=True)))


@app.get("/marketing/funnel", tags=["marketing"])
def marketing_funnel() -> Any:
    """Lead funnel metrics."""
    return j(core.marketing_funnel())


@app.get("/marketing/portal", tags=["marketing"], response_class=HTMLResponse)
def marketing_portal(lang: str = Depends(ui_lang), theme: str = Depends(ui_theme)) -> HTMLResponse:
    """The AI Marketing Conductor wing page (HTML)."""
    return HTMLResponse(content=core.marketing_portal(lang=lang, theme=theme))


@app.get("/marketing/portal.html", tags=["marketing"], response_class=HTMLResponse)
def marketing_portal_html(lang: str = Depends(ui_lang), theme: str = Depends(ui_theme)) -> HTMLResponse:
    """Alias of ``/marketing/portal`` that always serves HTML."""
    return HTMLResponse(content=core.marketing_portal(lang=lang, theme=theme))


# ==================================================================
# COMMERCIALIZATION
# ==================================================================


class RecommendPackageRequest(BaseModel):
    segment: str
    seats: int = 1
    expected_calls: int = 0
    product: Optional[str] = None


class SubscribeRequest(BaseModel):
    account: str
    plan_key: str
    seats: int = 1


class MeterUsageRequest(BaseModel):
    account: str
    tool: str
    units: int = 1
    product: Optional[str] = None
    unit_price: Optional[float] = None


class RevenueShareRequest(BaseModel):
    commission_gross: float
    platform_share: float = 0.20


class PayoutRequest(BaseModel):
    transaction_id: str
    gross_commission: float
    payee: str
    share_pct: float
    role: str = "agent"


@app.get("/commercial/products", tags=["commercial"])
def commercial_products(category: Optional[str] = None, priority: Optional[str] = None) -> Any:
    """The commercial product catalogue."""
    return j(core.commercial_products(category=category, priority=priority))


@app.get("/commercial/plans", tags=["commercial"])
def commercial_plans(product: Optional[str] = None) -> Any:
    """Subscription / usage plans."""
    return j(core.commercial_plans(product=product))


@app.get("/commercial/pricing", tags=["commercial"])
def commercial_pricing_matrix() -> Any:
    """The hybrid-pricing matrix and GTM playbook."""
    return j(core.commercial_pricing_matrix())


@app.get("/commercial/subscriptions", tags=["commercial"])
def commercial_subscriptions(account: Optional[str] = None) -> Any:
    """Active subscriptions."""
    return j(core.commercial_subscriptions(account=account))


@app.get("/commercial/gtm", tags=["commercial"])
def commercial_gtm() -> Any:
    """The go-to-market playbook."""
    return j(core.commercial_gtm())


@app.get("/commercial/products/{key}", tags=["commercial"])
def commercial_product(key: str) -> Any:
    """One commercial product by key."""
    return j(core.commercial_product(key))


@app.get("/commercial/plans/{key}", tags=["commercial"])
def commercial_plan(key: str) -> Any:
    """One pricing plan by key."""
    return j(core.commercial_plan(key))


@app.post("/commercial/recommend", tags=["commercial"])
def commercial_recommend_package(payload: RecommendPackageRequest) -> Any:
    """Recommend the best-fit plan for a segment and estimate the monthly bill."""
    return j(core.commercial_recommend_package(**payload.model_dump(exclude_none=True)))


@app.post("/commercial/subscribe", tags=["commercial"], status_code=201)
def commercial_subscribe(payload: SubscribeRequest) -> Any:
    """Create a subscription for an account on a plan."""
    return j(core.commercial_subscribe(**payload.model_dump(exclude_none=True)))


@app.post("/commercial/meter", tags=["commercial"], status_code=201)
def commercial_meter_usage(payload: MeterUsageRequest) -> Any:
    """Record a metered usage event for an account."""
    return j(core.commercial_meter_usage(**payload.model_dump(exclude_none=True)))


@app.get("/commercial/usage/{account}", tags=["commercial"])
def commercial_usage(account: str, days: int = 30) -> Any:
    """Usage summary for an account."""
    return j(core.commercial_usage(account, days=days))


@app.get("/commercial/bill/{account}", tags=["commercial"])
def commercial_bill(account: str, plan_key: Optional[str] = None, days: int = 30) -> Any:
    """A usage-based billing statement for an account."""
    return j(core.commercial_bill(account, plan_key=plan_key, days=days))


@app.post("/commercial/revenue-share", tags=["commercial"])
def commercial_revenue_share(payload: RevenueShareRequest) -> Any:
    """Split a commission into platform and partner shares."""
    return j(core.commercial_revenue_share(**payload.model_dump(exclude_none=True)))


@app.post("/commercial/payouts", tags=["commercial"], status_code=201)
def commercial_record_payout(payload: PayoutRequest) -> Any:
    """Record a payee payout against a transaction commission."""
    return j(core.commercial_record_payout(**payload.model_dump(exclude_none=True)))


@app.get("/commercial/payouts", tags=["commercial"])
def commercial_payouts(account: Optional[str] = None, status: Optional[str] = None) -> Any:
    """Recorded payouts."""
    return j(core.commercial_payouts(account=account, status=status))


@app.get("/commercial/portal", tags=["commercial"], response_class=HTMLResponse)
def commercial_portal(lang: str = Depends(ui_lang), theme: str = Depends(ui_theme)) -> HTMLResponse:
    """The Commercialization wing page (HTML)."""
    return HTMLResponse(content=core.commercial_portal(lang=lang, theme=theme))


@app.get("/commercial/portal.html", tags=["commercial"], response_class=HTMLResponse)
def commercial_portal_html(lang: str = Depends(ui_lang), theme: str = Depends(ui_theme)) -> HTMLResponse:
    """Alias of ``/commercial/portal`` that always serves HTML."""
    return HTMLResponse(content=core.commercial_portal(lang=lang, theme=theme))


# ==================================================================
# PRODUCT SURFACES: MCP-for-brokers & Property Intelligence
# ==================================================================


@app.get("/broker/contacts", tags=["broker"])
def search_contacts(query: Optional[str] = None, status: Optional[str] = None,
                    min_intent_score: Optional[float] = None,
                    lifecycle: Optional[str] = None, limit: int = 25) -> Any:
    """CRM contacts with live move-likelihood intent scoring (product: MCP for Brokers)."""
    return j(core.search_contacts(query=query, status=status, min_intent_score=min_intent_score,
                                  lifecycle=lifecycle, limit=limit))


@app.get("/broker/commission-projection", tags=["broker"])
def get_commission_projection(agent_id: Optional[str] = None, horizon_days: int = 90,
                              commission_rate: float = 0.02) -> Any:
    """Realised + weighted-pipeline commission projection from the live deal pipeline."""
    return j(core.get_commission_projection(agent_id=agent_id, horizon_days=horizon_days,
                                            commission_rate=commission_rate))


@app.get("/broker/property-gis", tags=["broker"])
def analyze_property_gis(property_id: Optional[str] = None, address: Optional[str] = None,
                         commute_destination: Optional[str] = None) -> Any:
    """GIS-enhanced property analysis (amenities, schools, safety, commute)."""
    return j(core.analyze_property_gis(property_id=property_id, address=address,
                                       commute_destination=commute_destination))


@app.get("/broker/listing-draft/{property_id}", tags=["broker"])
def create_listing_draft(property_id: str, tone: str = "professional", lang: str = "en") -> Any:
    """Draft a complete listing kit (headline, description, social posts, e-mail, video)."""
    return j(core.create_listing_draft(property_id, tone=tone, lang=lang))


@app.get("/property-intelligence/gis-score", tags=["property-intelligence"])
def get_gis_score(property_id: Optional[str] = None, address: Optional[str] = None,
                  destination: Optional[str] = None) -> Any:
    """The Property-Intelligence GIS score for an address or property (0–100 + grade)."""
    return j(core.get_gis_score(property_id=property_id, address=address, destination=destination))


@app.get("/property-intelligence/accounting-snapshot/{property_id}", tags=["property-intelligence"])
def get_accounting_snapshot(property_id: str, rental_yield: float = 0.045,
                            operating_expense_rate: float = 0.30) -> Any:
    """Per-property accounting snapshot: value, NOI, cap rate, ROI and active leases."""
    return j(core.get_accounting_snapshot(property_id, rental_yield=rental_yield,
                                          operating_expense_rate=operating_expense_rate))


@app.get("/property-intelligence/market-intelligence", tags=["property-intelligence"])
def get_market_intelligence(region: Optional[str] = None, years: int = 5) -> Any:
    """Regional market intelligence: pricing, factors, news momentum and forecast."""
    return j(core.get_market_intelligence(region=region, years=years))


@app.get("/property-intelligence/seller-intent/{contact_id}", tags=["property-intelligence"])
def score_seller_intent(contact_id: str, equity_pct: Optional[float] = None,
                        holding_years: Optional[float] = None, market_heat: float = 0.6,
                        life_event: Optional[str] = None, fsbo_signal: bool = False) -> Any:
    """Score a CRM contact's likelihood of selling (0–100) with reasons and next action."""
    return j(core.score_seller_intent(contact_id, equity_pct=equity_pct,
                                      holding_years=holding_years, market_heat=market_heat,
                                      life_event=life_event, fsbo_signal=fsbo_signal))


# ==================================================================
# TOOLS & UTILITIES WING
# ==================================================================


class ToolsMortgageRequest(BaseModel):
    price: float
    down_payment: float = 0.0
    annual_rate: Optional[float] = None
    years: Optional[int] = None
    payments_per_year: int = 12


class ToolsInstallmentRequest(BaseModel):
    price: float
    down_payment: float = 0.0
    months: int = 36
    annual_markup: float = 0.0


class ToolsRentalYieldRequest(BaseModel):
    price: float
    monthly_rent: float
    annual_costs: float = 0.0
    vacancy_rate: float = 0.0


class ToolsAppreciationRequest(BaseModel):
    current_value: float
    cagr: float = 0.08
    years: int = 10
    monthly_rent: float = 0.0
    rent_growth: float = 0.05


class ToolsPricePerUnitRequest(BaseModel):
    price: float
    area: float
    from_unit: str = "sqft"
    marla_sqft: float = 272.25


class ToolsTransferRequest(BaseModel):
    price: float
    province: str = "punjab"
    filer: bool = True
    rate_overrides: Optional[Dict[str, float]] = None


class ToolsCommissionRequest(BaseModel):
    price: float
    rate: Optional[float] = None
    include_vat: bool = True


class ToolsCgtRequest(BaseModel):
    gain: float
    holding_years: float
    filer: bool = True


class ToolsJointInvestmentRequest(BaseModel):
    partners: List[Dict[str, Any]]
    total_profit: float
    months: float = 12.0


class ToolsRentVsBuyRequest(BaseModel):
    price: float
    monthly_rent: float
    down_payment_pct: float = 0.20
    annual_rate: Optional[float] = None
    years: Optional[int] = None
    cagr: float = 0.08
    rent_growth: float = 0.05
    hold_years: int = 10


class ToolsConstructionRequest(BaseModel):
    covered_area: float
    floors: int = 1
    building_type: str = "house"
    quality_tier: str = "standard"
    system: str = "rcc_frame"
    city: Optional[str] = None
    plot_area: Optional[float] = None
    escalation_years: float = 0.0


class ToolsMaterialRequest(BaseModel):
    covered_area: float
    quality_tier: str = "standard"
    building_type: str = "house"


class ToolsTimelineRequest(BaseModel):
    covered_area: float
    floors: int = 1
    building_type: str = "house"
    system: str = "rcc_frame"


class ToolsMeasureRequest(BaseModel):
    coords: List[List[float]]
    marla_sqft: float = 272.25


class ToolsPolygonAreaRequest(BaseModel):
    coords: List[List[float]]
    unit: str = "sqft"
    marla_sqft: float = 272.25


class ToolsGeoreferenceRequest(BaseModel):
    control_points: List[Dict[str, Any]]


class ToolsTransformRequest(BaseModel):
    matrix: Dict[str, float]
    x: float
    y: float
    to_geo: bool = True


class ToolsAerialRequest(BaseModel):
    scenes: List[Dict[str, Any]]


class ToolsExportRequest(BaseModel):
    features: List[Dict[str, Any]]
    fmt: str = "geojson"
    name: str = "export"


class ToolsImportRequest(BaseModel):
    text: str


class ToolsNearbyRequest(BaseModel):
    origin: List[float]
    radius_m: float = 2000.0
    category: Optional[str] = None
    limit: int = 20


class ToolsCadInspectRequest(BaseModel):
    filename: str = ""
    head_base64: Optional[str] = None
    size_bytes: int = 0


class ToolsDxfRequest(BaseModel):
    text: str
    width: int = 800
    height: int = 600


class ToolsRevisionsRequest(BaseModel):
    a_entities: List[Dict[str, Any]]
    b_entities: List[Dict[str, Any]]


class ToolsLayoutRequest(BaseModel):
    title: str
    plot_length_ft: float
    plot_width_ft: float
    orientation: str = "portrait"


class ToolsGpsReadRequest(BaseModel):
    image_base64: str


class ToolsGpsWriteRequest(BaseModel):
    image_base64: str
    latitude: float
    longitude: float
    altitude: Optional[float] = None
    timestamp: Optional[str] = None


class ToolsGeotagBatchRequest(BaseModel):
    photos: List[Dict[str, Any]]
    latitude: float
    longitude: float
    altitude: Optional[float] = None


class ToolsPhotoReportRequest(BaseModel):
    photos: List[Dict[str, Any]]
    title: str = "Site photo report"


class ToolsTextPdfRequest(BaseModel):
    title: str
    lines: List[str]
    page_size: str = "a4"


class ToolsImagesPdfRequest(BaseModel):
    images: List[Dict[str, Any]]
    page_size: str = "a4"


class ToolsBrochureRequest(BaseModel):
    title: str
    subtitle: str = ""
    sections: Optional[List[Dict[str, Any]]] = None


class ToolsPdfInfoRequest(BaseModel):
    pdf_base64: str


class ToolsIcsRequest(BaseModel):
    events: List[Dict[str, Any]]
    calendar_name: str = "Arz-e-Pak"


class ToolsRemindersRequest(BaseModel):
    events: List[Dict[str, Any]]
    lead_days: int = 7


class ToolsMilestonesRequest(BaseModel):
    start_date: str
    covered_area: float = 1000.0
    floors: int = 1
    building_type: str = "house"
    system: str = "rcc_frame"


class ToolsPossessionRequest(BaseModel):
    start_date: str
    total_price: float
    down_payment: float = 0.0
    months: int = 24
    frequency: str = "monthly"


class ToolsComparisonRequest(BaseModel):
    properties: List[Dict[str, Any]]


class ToolsInvestmentRequest(BaseModel):
    initial_investment: float
    annual_cash_flow: float = 0.0
    hold_years: int = 10
    terminal_value: float = 0.0
    loan_amount: float = 0.0
    loan_rate: Optional[float] = None


class ToolsInventoryRequest(BaseModel):
    properties: List[Dict[str, Any]]
    marla_sqft: float = 272.25


class ToolsRowsRequest(BaseModel):
    rows: List[Dict[str, Any]]
    columns: Optional[List[str]] = None


class ToolsProjectRequest(BaseModel):
    name: str
    tool: str
    inputs: Optional[Dict[str, Any]] = None
    outputs: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None


@app.get("/tools/overview", tags=["tools"])
def tools_overview() -> Any:
    """Counts by category and phase for the Tools Center, plus configuration."""
    return j(core.tools_overview())


@app.get("/tools/categories", tags=["tools"])
def tools_categories() -> Any:
    """The Tools Center categories and their tool counts."""
    return j(core.tools_categories())


@app.get("/tools/catalog", tags=["tools"])
def tools_catalog(category: Optional[str] = None, phase: Optional[int] = None) -> Any:
    """The tool cards, optionally filtered by category or launch phase."""
    return j(core.tools_catalog(category=category, phase=phase))


@app.get("/tools/catalog/{key}", tags=["tools"])
def tool_get(key: str) -> Any:
    """One tool card by key (e.g. ``mortgage``, ``georeference``, ``calendar``)."""
    return j(core.tool_get(key))


@app.get("/tools/area-units", tags=["tools"])
def tool_area_units() -> Any:
    """Area units and marla standards supported by the converters."""
    return j(core.tool_area_units())


@app.get("/tools/convert/area", tags=["tools"])
def tool_area_convert(value: float, from_unit: str = "sqft", to_unit: str = "marla",
                      marla_sqft: float = 272.25) -> Any:
    """Convert between sqft / sqyd / sqm / marla / kanal / acre / hectare."""
    return j(core.tool_area_convert(value, from_unit=from_unit, to_unit=to_unit,
                                    marla_sqft=marla_sqft))


@app.get("/tools/convert/area-table", tags=["tools"])
def tool_area_table(value: float, from_unit: str = "sqft", marla_sqft: float = 272.25) -> Any:
    """Show an area in every supported unit at once."""
    return j(core.tool_area_table(value, from_unit=from_unit, marla_sqft=marla_sqft))


@app.get("/tools/convert/length", tags=["tools"])
def tool_length_convert(value: float, from_unit: str = "ft", to_unit: str = "m") -> Any:
    """Convert between feet, inches, yards, metres, centimetres and kilometres."""
    return j(core.tool_length_convert(value, from_unit=from_unit, to_unit=to_unit))


@app.get("/tools/plot/dimensions", tags=["tools"])
def tool_plot_dimensions(area: float, from_unit: str = "marla", ratio: float = 2.0,
                         marla_sqft: float = 272.25) -> Any:
    """Length / width / perimeter / diagonal of a rectangular plot from its area."""
    return j(core.tool_plot_dimensions(area, from_unit=from_unit, ratio=ratio,
                                       marla_sqft=marla_sqft))


@app.get("/tools/plot/studio", tags=["tools"])
def tool_plot_studio(value: float, from_unit: str = "marla", ratio: float = 2.0,
                     covered_area: Optional[float] = None, quality_tier: str = "standard",
                     building_type: str = "house", marla_sqft: float = 272.25) -> Any:
    """One-shot plot brief: conversion, dimensions, diagram and optional build cost."""
    return j(core.tool_plot_studio(value, from_unit=from_unit, ratio=ratio,
                                   covered_area=covered_area, quality_tier=quality_tier,
                                   building_type=building_type, marla_sqft=marla_sqft))


@app.get("/tools/plot/diagram", tags=["tools"])
def tool_plot_diagram(length_ft: float, width_ft: float, label: str = "Plot",
                      marla_sqft: float = 272.25) -> Any:
    """A printable SVG diagram of a rectangular plot with dimensions and area."""
    return j(core.tool_plot_diagram(length_ft, width_ft, label=label, marla_sqft=marla_sqft))


@app.get("/tools/calculators", tags=["tools"])
def tool_calculators() -> Any:
    """The calculators offered by the Tools Center, with their inputs and engines."""
    return j(core.tool_calculators())


@app.post("/tools/calculators/mortgage", tags=["tools"])
def tool_mortgage_calculator(payload: ToolsMortgageRequest) -> Any:
    """Home-loan monthly installment, total interest and full amortisation schedule."""
    return j(core.tool_mortgage_calculator(**payload.model_dump()))


@app.post("/tools/calculators/installment", tags=["tools"])
def tool_installment_plan(payload: ToolsInstallmentRequest) -> Any:
    """Developer-style installment plan: down payment, markup and monthly amount."""
    return j(core.tool_installment_plan(**payload.model_dump()))


@app.post("/tools/calculators/rental-yield", tags=["tools"])
def tool_rental_yield(payload: ToolsRentalYieldRequest) -> Any:
    """Gross and net rental yield with payback period and cap rate."""
    return j(core.tool_rental_yield(**payload.model_dump()))


@app.post("/tools/calculators/appreciation", tags=["tools"])
def tool_appreciation(payload: ToolsAppreciationRequest) -> Any:
    """Property appreciation and investment-growth projection with scenario bands."""
    return j(core.tool_appreciation(**payload.model_dump()))


@app.post("/tools/calculators/price-per-unit", tags=["tools"])
def tool_price_per_unit(payload: ToolsPricePerUnitRequest) -> Any:
    """Price per sqft / sqyd / sqm / marla for a listing."""
    return j(core.tool_price_per_unit(**payload.model_dump()))


@app.post("/tools/calculators/transfer-costs", tags=["tools"])
def tool_transfer_costs(payload: ToolsTransferRequest) -> Any:
    """Stamp duty, CVT, registration, mutation and withholding on a transfer."""
    return j(core.tool_transfer_costs(**payload.model_dump()))


@app.post("/tools/calculators/commission", tags=["tools"])
def tool_agent_commission(payload: ToolsCommissionRequest) -> Any:
    """Agent commission on a sale, with optional output VAT."""
    return j(core.tool_agent_commission(**payload.model_dump()))


@app.post("/tools/calculators/capital-gains", tags=["tools"])
def tool_capital_gains_tax(payload: ToolsCgtRequest) -> Any:
    """Capital-gains tax on a disposal, by holding period and filer status."""
    return j(core.tool_capital_gains_tax(**payload.model_dump()))


@app.post("/tools/calculators/joint-investment", tags=["tools"])
def tool_joint_investment(payload: ToolsJointInvestmentRequest) -> Any:
    """Split a profit between partners pro-rata to capital, with each partner's ROI."""
    return j(core.tool_joint_investment(**payload.model_dump()))


@app.post("/tools/calculators/rent-vs-buy", tags=["tools"])
def tool_rent_vs_buy(payload: ToolsRentVsBuyRequest) -> Any:
    """Compare buying against renting over a holding period."""
    return j(core.tool_rent_vs_buy(**payload.model_dump()))


@app.post("/tools/calculators/construction-cost", tags=["tools"])
def tool_construction_cost(payload: ToolsConstructionRequest) -> Any:
    """Construction-cost estimate (delegates to the construction wing's engine)."""
    return j(core.tool_construction_cost(**payload.model_dump()))


@app.post("/tools/calculators/material-quantities", tags=["tools"])
def tool_material_quantities(payload: ToolsMaterialRequest) -> Any:
    """Approximate material take-off (delegates to the construction wing)."""
    return j(core.tool_material_quantities(**payload.model_dump()))


@app.post("/tools/calculators/build-timeline", tags=["tools"])
def tool_build_timeline(payload: ToolsTimelineRequest) -> Any:
    """Phase-weighted construction timeline (delegates to the construction wing)."""
    return j(core.tool_build_timeline(**payload.model_dump()))


@app.get("/tools/gis/crs", tags=["tools"])
def tool_crs_catalog() -> Any:
    """Common coordinate reference systems with measurement guidance."""
    return j(core.tool_crs_catalog())


@app.post("/tools/gis/measure", tags=["tools"])
def tool_map_measure(payload: ToolsMeasureRequest) -> Any:
    """Distance, perimeter, area, centroid and bbox for [lat, lon] points."""
    return j(core.tool_map_measure(**payload.model_dump()))


@app.post("/tools/gis/polygon-area", tags=["tools"])
def tool_polygon_area(payload: ToolsPolygonAreaRequest) -> Any:
    """Area of a polygon from its [lat, lon] coordinates, in the requested unit."""
    return j(core.tool_polygon_area(**payload.model_dump()))


@app.post("/tools/gis/georeference", tags=["tools"])
def tool_georeference(payload: ToolsGeoreferenceRequest) -> Any:
    """Fit an image-pixel → WGS84 transform from control points (affine/similarity)."""
    return j(core.tool_georeference(**payload.model_dump()))


@app.post("/tools/gis/transform", tags=["tools"])
def tool_transform_point(payload: ToolsTransformRequest) -> Any:
    """Apply a georeference matrix (px→geo forward, or geo→px with to_geo=False)."""
    return j(core.tool_transform_point(**payload.model_dump()))


@app.post("/tools/gis/aerial-compare", tags=["tools"])
def tool_aerial_compare(payload: ToolsAerialRequest) -> Any:
    """Compare dated aerial/satellite scenes: order, resolution and change."""
    return j(core.tool_aerial_compare(**payload.model_dump()))


@app.post("/tools/gis/export", tags=["tools"])
def tool_export_geodata(payload: ToolsExportRequest) -> Any:
    """Export points/lines/polygons as GeoJSON or KML."""
    return j(core.tool_export_geodata(**payload.model_dump()))


@app.post("/tools/gis/import", tags=["tools"])
def tool_import_geodata(payload: ToolsImportRequest) -> Any:
    """Parse GeoJSON or KML text into [lat, lon] coordinate lists."""
    return j(core.tool_import_geodata(**payload.model_dump()))


@app.post("/tools/gis/nearby", tags=["tools"])
def tool_locate_nearby(payload: ToolsNearbyRequest) -> Any:
    """Locate POIs within a radius of an origin [lat, lon], nearest first."""
    return j(core.tool_locate_nearby(**payload.model_dump()))


@app.get("/tools/cad/formats", tags=["tools"])
def tool_cad_formats() -> Any:
    """Supported drawing formats and what each can actually preview/convert."""
    return j(core.tool_cad_formats())


@app.post("/tools/cad/inspect", tags=["tools"])
def tool_cad_inspect(payload: ToolsCadInspectRequest) -> Any:
    """Detect a drawing's format from its name/first bytes and report capabilities."""
    return j(core.tool_cad_inspect(**payload.model_dump()))


@app.post("/tools/cad/dxf-preview", tags=["tools"])
def tool_dxf_preview(payload: ToolsDxfRequest) -> Any:
    """Parse an ASCII DXF and render it to SVG (line/polyline/circle/text)."""
    return j(core.tool_dxf_preview(**payload.model_dump()))


@app.post("/tools/cad/compare-revisions", tags=["tools"])
def tool_compare_revisions(payload: ToolsRevisionsRequest) -> Any:
    """Compare two revisions of a plan: counts, extents and added/removed items."""
    return j(core.tool_compare_revisions(**payload.model_dump()))


@app.post("/tools/cad/layout-sheet", tags=["tools"])
def tool_printable_layout(payload: ToolsLayoutRequest) -> Any:
    """A printable plot-layout sheet (SVG) with a title block and scale bar."""
    return j(core.tool_printable_layout(**payload.model_dump()))


@app.post("/tools/photo/read-gps", tags=["tools"])
def tool_read_photo_gps(payload: ToolsGpsReadRequest) -> Any:
    """Read GPS coordinates, altitude and time from a JPEG's EXIF metadata."""
    return j(core.tool_read_photo_gps(**payload.model_dump()))


@app.post("/tools/photo/write-gps", tags=["tools"])
def tool_write_photo_gps(payload: ToolsGpsWriteRequest) -> Any:
    """Embed/replace GPS coordinates in a JPEG's EXIF (returns new base64 bytes)."""
    return j(core.tool_write_photo_gps(**payload.model_dump()))


@app.post("/tools/photo/geotag-batch", tags=["tools"])
def tool_photo_geotag_batch(payload: ToolsGeotagBatchRequest) -> Any:
    """Geotag several photos with the same coordinate."""
    return j(core.tool_photo_geotag_batch(**payload.model_dump()))


@app.post("/tools/photo/report", tags=["tools"])
def tool_photo_report(payload: ToolsPhotoReportRequest) -> Any:
    """A property photo report: markers, summary table and an embeddable map."""
    return j(core.tool_photo_report(**payload.model_dump()))


@app.get("/tools/photo/privacy-check", tags=["tools"])
def tool_geo_privacy_check(latitude: float, longitude: float) -> Any:
    """Advise on sharing precise residential coordinates (opt-in, fuzzing)."""
    return j(core.tool_geo_privacy_check(latitude, longitude))


@app.get("/tools/documents/tools", tags=["tools"])
def tool_document_tools() -> Any:
    """The document/conversion tools and whether each is native or needs a dependency."""
    return j(core.tool_document_tools())


@app.get("/tools/documents/convert-guide", tags=["tools"])
def tool_convert_guide(kind: str) -> Any:
    """Explain what a heavier conversion needs (and why), plus upload-safety notes."""
    return j(core.tool_convert_guide(kind))


@app.post("/tools/documents/text-to-pdf", tags=["tools"])
def tool_text_to_pdf(payload: ToolsTextPdfRequest) -> Any:
    """Create a simple text/listings PDF (dependency-free)."""
    return j(core.tool_text_to_pdf(**payload.model_dump()))


@app.post("/tools/documents/images-to-pdf", tags=["tools"])
def tool_images_to_pdf(payload: ToolsImagesPdfRequest) -> Any:
    """Combine JPEG images into a PDF (native, no re-encoding)."""
    return j(core.tool_images_to_pdf(**payload.model_dump()))


@app.post("/tools/documents/brochure", tags=["tools"])
def tool_brochure_pdf(payload: ToolsBrochureRequest) -> Any:
    """Build a branded text brochure PDF from a list of sections."""
    return j(core.tool_brochure_pdf(**payload.model_dump()))


@app.post("/tools/documents/pdf-info", tags=["tools"])
def tool_pdf_info(payload: ToolsPdfInfoRequest) -> Any:
    """Basic PDF inspection: page count and declared size."""
    return j(core.tool_pdf_info(**payload.model_dump()))


@app.get("/tools/documents/resize-plan", tags=["tools"])
def tool_image_resize_plan(width: int, height: int, max_width: int = 1600,
                           max_height: int = 1600) -> Any:
    """Compute a contain-fit resize target without touching the pixels."""
    return j(core.tool_image_resize_plan(width, height, max_width=max_width, max_height=max_height))


@app.get("/tools/calendar/hijri", tags=["tools"])
def tool_hijri_from_gregorian(on: str) -> Any:
    """Convert a Gregorian date (YYYY-MM-DD) to the predicted Hijri date."""
    return j(core.tool_hijri_from_gregorian(on))


@app.get("/tools/calendar/gregorian", tags=["tools"])
def tool_gregorian_from_hijri(year: int, month: int, day: int) -> Any:
    """Convert a Hijri date to the predicted Gregorian date."""
    return j(core.tool_gregorian_from_hijri(year, month, day))


@app.get("/tools/calendar/occasions", tags=["tools"])
def tool_islamic_occasions(year: int) -> Any:
    """The main Islamic occasions inside a Gregorian year (predicted)."""
    return j(core.tool_islamic_occasions(year))


@app.get("/tools/calendar/holidays", tags=["tools"])
def tool_pakistan_holidays(year: int) -> Any:
    """Pakistan public holidays for a year: fixed national days + predicted Islamic ones."""
    return j(core.tool_pakistan_holidays(year))


@app.post("/tools/calendar/ics", tags=["tools"])
def tool_calendar_ics(payload: ToolsIcsRequest) -> Any:
    """Render events as a downloadable iCalendar (.ics) feed."""
    return j(core.tool_calendar_ics(**payload.model_dump()))


@app.post("/tools/calendar/reminders", tags=["tools"])
def tool_property_reminders(payload: ToolsRemindersRequest) -> Any:
    """Turn dated property events into reminders (possession, installments, expiries)."""
    return j(core.tool_property_reminders(**payload.model_dump()))


@app.post("/tools/calendar/milestones", tags=["tools"])
def tool_milestone_calendar(payload: ToolsMilestonesRequest) -> Any:
    """Date-stamp a construction timeline into a milestone calendar (+ .ics)."""
    return j(core.tool_milestone_calendar(**payload.model_dump()))


@app.post("/tools/calendar/possession", tags=["tools"])
def tool_possession_schedule(payload: ToolsPossessionRequest) -> Any:
    """A booking + installment + possession payment schedule with due dates (+ .ics)."""
    return j(core.tool_possession_schedule(**payload.model_dump()))


@app.post("/tools/reports/comparison", tags=["tools"])
def tool_property_comparison(payload: ToolsComparisonRequest) -> Any:
    """Side-by-side comparison of listings with derived price/sqft and yield."""
    return j(core.tool_property_comparison(**payload.model_dump()))


@app.post("/tools/reports/investment-summary", tags=["tools"])
def tool_investment_summary(payload: ToolsInvestmentRequest) -> Any:
    """Investment summary built on the accounting ROI engine (with scenarios)."""
    return j(core.tool_investment_summary(**payload.model_dump()))


@app.post("/tools/reports/plot-inventory", tags=["tools"])
def tool_plot_inventory(payload: ToolsInventoryRequest) -> Any:
    """Plot inventory: area in sqft / marla / kanal with price per unit."""
    return j(core.tool_plot_inventory(**payload.model_dump()))


@app.post("/tools/reports/csv", tags=["tools"])
def tool_rows_to_csv(payload: ToolsRowsRequest) -> Any:
    """Serialise rows of dicts to CSV text."""
    return j(core.tool_rows_to_csv(**payload.model_dump()))


@app.post("/tools/reports/markdown", tags=["tools"])
def tool_rows_to_markdown(payload: ToolsRowsRequest) -> Any:
    """Serialise rows of dicts to a Markdown table."""
    return j(core.tool_rows_to_markdown(**payload.model_dump()))


@app.get("/tools/projects", tags=["tools"])
def tool_projects(tool: Optional[str] = None) -> Any:
    """List saved tool projects, optionally filtered by tool key."""
    return j(core.tool_projects(tool=tool))


@app.post("/tools/projects", tags=["tools"])
def tool_save_project(payload: ToolsProjectRequest) -> Any:
    """Save a tool run as a reusable project (personalised tools)."""
    return j(core.tool_save_project(**payload.model_dump()))


@app.get("/tools/projects/{project_id}", tags=["tools"])
def tool_project_get(project_id: str) -> Any:
    """One saved tool project by id."""
    return j(core.tool_project_get(project_id))


@app.delete("/tools/projects/{project_id}", tags=["tools"])
def tool_project_delete(project_id: str) -> Any:
    """Delete a saved tool project."""
    return j(core.tool_project_delete(project_id))


@app.get("/tools/portal", tags=["tools"], response_class=HTMLResponse)
def tools_portal(lang: str = Depends(ui_lang), theme: str = Depends(ui_theme)) -> HTMLResponse:
    """The Tools & Utilities page (HTML): Tools Center, calculators, reference tables."""
    return HTMLResponse(content=core.tools_portal(lang=lang, theme=theme))


@app.get("/tools/portal.html", tags=["tools"], response_class=HTMLResponse)
def tools_portal_html(lang: str = Depends(ui_lang), theme: str = Depends(ui_theme)) -> HTMLResponse:
    """Alias of ``/tools/portal`` that always serves HTML."""
    return HTMLResponse(content=core.tools_portal(lang=lang, theme=theme))


# ==================================================================
# PMO WING (project management, monitoring & tracking)
# ==================================================================


class PmoProjectRequest(BaseModel):
    name: str
    project_type: str = "construction"
    description: Optional[str] = None
    city: Optional[str] = None
    scheme: Optional[str] = None
    client: Optional[str] = None
    manager_id: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    budget: float = 0.0
    contract_value: float = 0.0
    priority: str = "medium"
    status: str = "planning"
    tags: Optional[List[str]] = None
    with_template: bool = True


class PmoUpdatesRequest(BaseModel):
    updates: Dict[str, Any]


class PmoPhaseRequest(BaseModel):
    name: str
    key: Optional[str] = None
    weight: float = 0.0
    order: Optional[int] = None
    planned_start: Optional[str] = None
    planned_end: Optional[str] = None


class PmoMilestoneRequest(BaseModel):
    name: str
    planned_date: Optional[str] = None
    phase_key: Optional[str] = None
    task_id: Optional[str] = None
    weight: float = 1.0
    billable_amount: float = 0.0
    notes: Optional[str] = None


class PmoTaskRequest(BaseModel):
    name: str
    phase_key: Optional[str] = None
    duration_days: int = 1
    predecessors: Optional[List[str]] = None
    assignee_id: Optional[str] = None
    weight: float = 0.0
    cost_budget: float = 0.0
    priority: str = "medium"
    wbs: Optional[str] = None
    notes: Optional[str] = None


class PmoCostRequest(BaseModel):
    amount: float
    category: str = "other"
    description: str = ""
    kind: str = "actual"
    date: Optional[str] = None
    vendor: Optional[str] = None
    invoice_ref: Optional[str] = None
    recorded_by: Optional[str] = None


class PmoProgressRequest(BaseModel):
    percent: float
    note: Optional[str] = None
    by: Optional[str] = None
    manpower: int = 0
    weather: Optional[str] = None
    on: Optional[str] = None


class PmoResourceRequest(BaseModel):
    name: str
    role: str = "engineer"
    trade: Optional[str] = None
    day_rate: float = 0.0
    capacity_pct: float = 100.0
    skills: Optional[List[str]] = None
    contact: Optional[str] = None


class PmoAssignRequest(BaseModel):
    task_id: str
    resource_id: str
    units_pct: float = 100.0
    notes: Optional[str] = None


class PmoRiskRequest(BaseModel):
    title: str
    kind: str = "risk"
    probability: int = 3
    impact: int = 3
    description: Optional[str] = None
    category: Optional[str] = None
    owner: Optional[str] = None
    mitigation: Optional[str] = None
    due_on: Optional[str] = None


class PmoSiteLogRequest(BaseModel):
    date: Optional[str] = None
    weather: Optional[str] = None
    manpower: int = 0
    equipment: Optional[List[str]] = None
    work_done: Optional[str] = None
    issues: Optional[str] = None
    safety_incidents: int = 0
    visitors: Optional[str] = None
    photos: Optional[List[str]] = None
    by: Optional[str] = None


class PmoChangeRequest(BaseModel):
    title: str
    description: Optional[str] = None
    reason: Optional[str] = None
    cost_impact: float = 0.0
    schedule_impact_days: int = 0
    requested_by: Optional[str] = None
    status: str = "submitted"


class PmoChangeDecisionRequest(BaseModel):
    approve: bool = True
    by: Optional[str] = None
    note: Optional[str] = None


class PmoInspectionRequest(BaseModel):
    title: str
    checklist: Optional[List[Dict[str, Any]]] = None
    phase_key: Optional[str] = None
    area: Optional[str] = None
    inspector: Optional[str] = None
    date: Optional[str] = None
    status: str = "open"
    notes: Optional[str] = None


class PmoActionRequest(BaseModel):
    title: str
    owner: Optional[str] = None
    due_on: Optional[str] = None
    priority: str = "medium"
    meeting: Optional[str] = None
    notes: Optional[str] = None


@app.get("/pmo/overview", tags=["pmo"])
def pmo_overview() -> Any:
    """Counts, breakdowns and configuration for the PMO wing."""
    return j(core.pmo_overview())


@app.get("/pmo/capabilities", tags=["pmo"])
def pmo_capabilities() -> Any:
    """The PMO capabilities grouped by category."""
    return j(core.pmo_capabilities())


@app.get("/pmo/project-types", tags=["pmo"])
def pmo_project_types() -> Any:
    """The supported project types, statuses and priorities."""
    return j(core.pm_project_types())


@app.get("/pmo/phase-templates", tags=["pmo"])
def pmo_phase_templates(project_type: Optional[str] = Query(default=None)) -> Any:
    """Default weighted phase templates by project type."""
    return j(core.pm_phase_templates(project_type))


@app.get("/pmo/projects", tags=["pmo"])
def pmo_projects(status: Optional[str] = None, project_type: Optional[str] = None,
                 city: Optional[str] = None, manager_id: Optional[str] = None,
                 priority: Optional[str] = None, limit: int = 50) -> Any:
    """List projects with progress and health."""
    return j(core.pm_projects(status=status, project_type=project_type, city=city,
                              manager_id=manager_id, priority=priority, limit=limit))


@app.post("/pmo/projects", tags=["pmo"])
def pmo_create_project(payload: PmoProjectRequest) -> Any:
    """Register a project (optionally seeding its phases and WBS template)."""
    return j(core.pm_create_project(**payload.model_dump()))


@app.post("/pmo/from-estimate/{estimate_id}", tags=["pmo"])
def pmo_from_estimate(estimate_id: str, name: Optional[str] = None, city: Optional[str] = None,
                      start_date: Optional[str] = None, contract_value: Optional[float] = None) -> Any:
    """Create a delivery project from a saved Construction-wing estimate."""
    return j(core.pm_from_estimate(estimate_id, name=name, city=city, start_date=start_date,
                                   contract_value=contract_value))


@app.get("/pmo/projects/{project_id}", tags=["pmo"])
def pmo_project(project_id: str) -> Any:
    """One project by id or code, with its counts."""
    return j(core.pm_project(project_id))


@app.put("/pmo/projects/{project_id}", tags=["pmo"])
def pmo_update_project(project_id: str, payload: PmoUpdatesRequest) -> Any:
    """Update a project's fields."""
    return j(core.pm_update_project(project_id, payload.updates or {}))


@app.delete("/pmo/projects/{project_id}", tags=["pmo"])
def pmo_delete_project(project_id: str) -> Any:
    """Delete a project and everything that belongs to it."""
    return j(core.pm_delete_project(project_id))


@app.get("/pmo/projects/{project_id}/dashboard", tags=["pmo"])
def pmo_project_dashboard(project_id: str) -> Any:
    """The full project-controls snapshot."""
    return j(core.pm_project_dashboard(project_id))


@app.get("/pmo/projects/{project_id}/report", tags=["pmo"])
def pmo_project_report(project_id: str) -> Any:
    """A full project status report as structured data."""
    return j(core.pm_project_report(project_id))


@app.post("/pmo/projects/{project_id}/apply-template", tags=["pmo"])
def pmo_apply_template(project_id: str, project_type: Optional[str] = None) -> Any:
    """Seed the project's phases and WBS from its type template."""
    return j(core.pm_apply_template(project_id, project_type))


@app.get("/pmo/projects/{project_id}/phases", tags=["pmo"])
def pmo_phases(project_id: str) -> Any:
    """List the project's phases."""
    return j(core.pm_phases(project_id))


@app.post("/pmo/projects/{project_id}/phases", tags=["pmo"])
def pmo_add_phase(project_id: str, payload: PmoPhaseRequest) -> Any:
    """Add a phase to the project."""
    return j(core.pm_add_phase(project_id, **payload.model_dump()))


@app.get("/pmo/projects/{project_id}/milestones", tags=["pmo"])
def pmo_milestones(project_id: str, status: Optional[str] = None) -> Any:
    """List the project's milestones."""
    return j(core.pm_milestones(project_id, status=status))


@app.post("/pmo/projects/{project_id}/milestones", tags=["pmo"])
def pmo_add_milestone(project_id: str, payload: PmoMilestoneRequest) -> Any:
    """Add a milestone."""
    return j(core.pm_add_milestone(project_id, **payload.model_dump()))


@app.get("/pmo/projects/{project_id}/tasks", tags=["pmo"])
def pmo_tasks(project_id: str, phase_key: Optional[str] = None, status: Optional[str] = None,
              assignee_id: Optional[str] = None) -> Any:
    """List the project's tasks with schedule data."""
    return j(core.pm_tasks(project_id, phase_key=phase_key, status=status, assignee_id=assignee_id))


@app.post("/pmo/projects/{project_id}/tasks", tags=["pmo"])
def pmo_add_task(project_id: str, payload: PmoTaskRequest) -> Any:
    """Add a task."""
    return j(core.pm_add_task(project_id, **payload.model_dump()))


@app.get("/pmo/tasks/{task_id}", tags=["pmo"])
def pmo_task(task_id: str) -> Any:
    """One task by id."""
    return j(core.pm_task(task_id))


@app.put("/pmo/tasks/{task_id}", tags=["pmo"])
def pmo_update_task(task_id: str, payload: PmoUpdatesRequest) -> Any:
    """Update a task."""
    return j(core.pm_update_task(task_id, payload.updates or {}))


@app.delete("/pmo/tasks/{task_id}", tags=["pmo"])
def pmo_delete_task(task_id: str) -> Any:
    """Delete a task."""
    return j(core.pm_delete_task(task_id))


@app.get("/pmo/projects/{project_id}/schedule", tags=["pmo"])
def pmo_schedule(project_id: str, start_date: Optional[str] = None) -> Any:
    """The forward/backward schedule with float and the critical path."""
    return j(core.pm_schedule(project_id, start_date=start_date))


@app.get("/pmo/projects/{project_id}/critical-path", tags=["pmo"])
def pmo_critical_path(project_id: str) -> Any:
    """The critical path for the project."""
    return j(core.pm_critical_path(project_id))


@app.get("/pmo/projects/{project_id}/gantt", tags=["pmo"])
def pmo_gantt(project_id: str) -> Any:
    """Gantt-ready rows for the project."""
    return j(core.pm_gantt(project_id))


@app.get("/pmo/projects/{project_id}/costs", tags=["pmo"])
def pmo_costs(project_id: str, kind: Optional[str] = None, category: Optional[str] = None) -> Any:
    """List the project's cost entries."""
    return j(core.pm_costs(project_id, kind=kind, category=category))


@app.post("/pmo/projects/{project_id}/costs", tags=["pmo"])
def pmo_add_cost(project_id: str, payload: PmoCostRequest) -> Any:
    """Record a cost entry against the project."""
    return j(core.pm_add_cost(project_id, **payload.model_dump()))


@app.get("/pmo/projects/{project_id}/progress", tags=["pmo"])
def pmo_progress(project_id: str) -> Any:
    """The project's actual vs planned completion, with history."""
    return j(core.pm_progress(project_id))


@app.post("/pmo/projects/{project_id}/progress", tags=["pmo"])
def pmo_record_progress(project_id: str, payload: PmoProgressRequest) -> Any:
    """Record a dated progress update."""
    return j(core.pm_record_progress(project_id, **payload.model_dump()))


@app.get("/pmo/projects/{project_id}/earned-value", tags=["pmo"])
def pmo_earned_value(project_id: str, as_of: Optional[str] = None) -> Any:
    """The earned-value analysis (PV/EV/AC/SPI/CPI/EAC …)."""
    return j(core.pm_earned_value(project_id, as_of=as_of))


@app.get("/pmo/projects/{project_id}/cost-status", tags=["pmo"])
def pmo_cost_status(project_id: str) -> Any:
    """The cost-control status."""
    return j(core.pm_cost_status(project_id))


@app.get("/pmo/projects/{project_id}/s-curve", tags=["pmo"])
def pmo_s_curve(project_id: str, weeks: int = 52) -> Any:
    """The planned-vs-actual S-curve."""
    return j(core.pm_s_curve(project_id, weeks=weeks))


@app.get("/pmo/projects/{project_id}/health", tags=["pmo"])
def pmo_health(project_id: str) -> Any:
    """The project's RAG health."""
    return j(core.pm_health(project_id))


@app.get("/pmo/projects/{project_id}/kpi", tags=["pmo"])
def pmo_kpi(project_id: str) -> Any:
    """The project's KPI scorecard."""
    return j(core.pm_kpi(project_id))


@app.get("/pmo/projects/{project_id}/monitoring", tags=["pmo"])
def pmo_monitoring(project_id: str) -> Any:
    """The project-controls monitoring snapshot."""
    return j(core.pm_monitoring(project_id))


@app.get("/pmo/projects/{project_id}/risks", tags=["pmo"])
def pmo_project_risks(project_id: str, kind: Optional[str] = None, status: Optional[str] = None,
                      min_score: int = 0) -> Any:
    """List the project's RAID items."""
    return j(core.pm_risks(project_id, kind=kind, status=status, min_score=min_score))


@app.post("/pmo/projects/{project_id}/risks", tags=["pmo"])
def pmo_add_risk(project_id: str, payload: PmoRiskRequest) -> Any:
    """Add a RAID item."""
    return j(core.pm_add_risk(project_id, **payload.model_dump()))


@app.get("/pmo/projects/{project_id}/risk-matrix", tags=["pmo"])
def pmo_risk_matrix(project_id: Optional[str] = None) -> Any:
    """The probability × impact risk matrix."""
    return j(core.pm_risk_matrix(project_id))


@app.get("/pmo/projects/{project_id}/site-logs", tags=["pmo"])
def pmo_site_logs(project_id: str, limit: int = 30) -> Any:
    """List the project's site diary entries."""
    return j(core.pm_site_logs(project_id, limit=limit))


@app.post("/pmo/projects/{project_id}/site-logs", tags=["pmo"])
def pmo_log_site(project_id: str, payload: PmoSiteLogRequest) -> Any:
    """Record a site diary entry."""
    return j(core.pm_log_site(project_id, **payload.model_dump()))


@app.get("/pmo/projects/{project_id}/site-report", tags=["pmo"])
def pmo_site_report(project_id: str, on: Optional[str] = None) -> Any:
    """A daily site report."""
    return j(core.pm_site_report(project_id, on=on))


@app.get("/pmo/projects/{project_id}/changes", tags=["pmo"])
def pmo_changes(project_id: str, status: Optional[str] = None) -> Any:
    """List the project's change requests."""
    return j(core.pm_changes(project_id, status=status))


@app.post("/pmo/projects/{project_id}/changes", tags=["pmo"])
def pmo_raise_change(project_id: str, payload: PmoChangeRequest) -> Any:
    """Raise a change request."""
    return j(core.pm_raise_change(project_id, **payload.model_dump()))


@app.post("/pmo/changes/{change_id}/decide", tags=["pmo"])
def pmo_decide_change(change_id: str, payload: PmoChangeDecisionRequest) -> Any:
    """Approve or reject a change request."""
    return j(core.pm_decide_change(change_id, **payload.model_dump()))


@app.get("/pmo/projects/{project_id}/inspections", tags=["pmo"])
def pmo_inspections(project_id: str, status: Optional[str] = None) -> Any:
    """List the project's inspections and quality index."""
    return j(core.pm_inspections(project_id, status=status))


@app.post("/pmo/projects/{project_id}/inspections", tags=["pmo"])
def pmo_add_inspection(project_id: str, payload: PmoInspectionRequest) -> Any:
    """Record an inspection."""
    return j(core.pm_add_inspection(project_id, **payload.model_dump()))


@app.get("/pmo/projects/{project_id}/actions", tags=["pmo"])
def pmo_project_actions(project_id: str, status: Optional[str] = None) -> Any:
    """List the project's action items."""
    return j(core.pm_actions(project_id=project_id, status=status))


@app.post("/pmo/projects/{project_id}/actions", tags=["pmo"])
def pmo_add_action(project_id: str, payload: PmoActionRequest) -> Any:
    """Add an action item."""
    return j(core.pm_add_action(project_id, **payload.model_dump()))


@app.get("/pmo/resources", tags=["pmo"])
def pmo_resources(trade: Optional[str] = None, active_only: bool = False) -> Any:
    """List resources."""
    return j(core.pm_resources(trade=trade, active_only=active_only))


@app.post("/pmo/resources", tags=["pmo"])
def pmo_add_resource(payload: PmoResourceRequest) -> Any:
    """Register a resource."""
    return j(core.pm_add_resource(**payload.model_dump()))


@app.post("/pmo/allocations", tags=["pmo"])
def pmo_assign(payload: PmoAssignRequest) -> Any:
    """Assign a resource to a task."""
    return j(core.pm_assign(**payload.model_dump()))


@app.get("/pmo/resource-load", tags=["pmo"])
def pmo_resource_load(project_id: Optional[str] = None, window_start: Optional[str] = None,
                      window_end: Optional[str] = None) -> Any:
    """Planned resource utilisation with over-allocation flags."""
    return j(core.pm_resource_load(project_id=project_id, window_start=window_start,
                                   window_end=window_end))


@app.get("/pmo/alerts", tags=["pmo"])
def pmo_alerts(project_id: Optional[str] = None) -> Any:
    """Exception-based alerts for one project or the portfolio."""
    return j(core.pm_alerts(project_id))


@app.get("/pmo/portfolio", tags=["pmo"])
def pmo_portfolio() -> Any:
    """The rolled-up portfolio dashboard."""
    return j(core.pm_portfolio())


@app.get("/pmo/risks", tags=["pmo"])
def pmo_risks(project_id: Optional[str] = None, kind: Optional[str] = None,
              status: Optional[str] = None, min_score: int = 0) -> Any:
    """List RAID items across the portfolio."""
    return j(core.pm_risks(project_id=project_id, kind=kind, status=status, min_score=min_score))


@app.put("/pmo/risks/{risk_id}", tags=["pmo"])
def pmo_update_risk(risk_id: str, payload: PmoUpdatesRequest) -> Any:
    """Update a RAID item."""
    return j(core.pm_update_risk(risk_id, payload.updates or {}))


@app.get("/pmo/actions", tags=["pmo"])
def pmo_actions(project_id: Optional[str] = None, status: Optional[str] = None) -> Any:
    """List action items."""
    return j(core.pm_actions(project_id=project_id, status=status))


@app.post("/pmo/actions/{action_id}/close", tags=["pmo"])
def pmo_close_action(action_id: str, status: str = "done") -> Any:
    """Close a meeting action item."""
    return j(core.pm_close_action(action_id, status=status))


@app.get("/pmo/report.html", tags=["pmo"], response_class=HTMLResponse)
def pmo_report_html(project_id: str, lang: str = Depends(ui_lang),
                    theme: str = Depends(ui_theme)) -> HTMLResponse:
    """A printable project status report (HTML)."""
    return HTMLResponse(content=core.pm_report_html(project_id, lang=lang, theme=theme))


@app.get("/pmo/portal", tags=["pmo"], response_class=HTMLResponse)
def pmo_portal(lang: str = Depends(ui_lang), theme: str = Depends(ui_theme)) -> HTMLResponse:
    """The Projects & Monitoring (PMO) page (HTML)."""
    return HTMLResponse(content=core.pmo_portal(lang=lang, theme=theme))


@app.get("/pmo/portal.html", tags=["pmo"], response_class=HTMLResponse)
def pmo_portal_html(lang: str = Depends(ui_lang), theme: str = Depends(ui_theme)) -> HTMLResponse:
    """Alias of ``/pmo/portal`` that always serves HTML."""
    return HTMLResponse(content=core.pmo_portal(lang=lang, theme=theme))


# ==================================================================
# TEAM MESSAGING & NOTIFICATIONS  (reuses server.py / messaging.py)
# ==================================================================


class MsgPresenceRequest(BaseModel):
    user_id: str
    presence: str = "online"


class MsgPreferencesRequest(BaseModel):
    prefs: Optional[Dict[str, List[str]]] = None
    quiet_hours: Optional[Dict[str, str]] = None
    digest: Optional[str] = None
    telegram_opt_in: Optional[bool] = None
    telegram_categories: Optional[List[str]] = None


class MsgConversationRequest(BaseModel):
    kind: str = "group"
    title: str = ""
    created_by: Optional[str] = None
    participants: Optional[List[str]] = None
    channel_key: Optional[str] = None
    property_id: Optional[str] = None
    topic: Optional[str] = None
    restricted: Optional[bool] = None
    roles_allowed: Optional[List[str]] = None
    retention_days: Optional[int] = None
    announcement: Optional[str] = None


class MsgDirectRequest(BaseModel):
    user_a: str
    user_b: str


class MsgPropertyThreadRequest(BaseModel):
    property_id: str
    created_by: Optional[str] = None
    title: Optional[str] = None


class MsgArchiveRequest(BaseModel):
    user_id: str
    archived: bool = True


class MsgMemberRequest(BaseModel):
    member_id: str
    actor_id: Optional[str] = None
    role: str = "member"


class MsgMemberUpdateRequest(BaseModel):
    actor_id: Optional[str] = None
    role: Optional[str] = None
    muted: Optional[bool] = None
    pinned: Optional[bool] = None
    notification_level: Optional[str] = None


class MsgRevokeRequest(BaseModel):
    user_id: str
    actor_id: Optional[str] = None
    reason: Optional[str] = None


class MsgPostRequest(BaseModel):
    author_id: str
    body: str = ""
    message_type: str = "text"
    parent_id: Optional[str] = None
    mentions: Optional[List[str]] = None
    attachment_ids: Optional[List[str]] = None
    property_id: Optional[str] = None


class MsgEditRequest(BaseModel):
    user_id: str
    body: str


class MsgReactRequest(BaseModel):
    user_id: str
    emoji: str


class MsgPinRequest(BaseModel):
    user_id: str
    pinned: bool = True


class MsgReadRequest(BaseModel):
    user_id: str
    up_to_seq: Optional[int] = None


class MsgAttachmentRequest(BaseModel):
    uploaded_by: str
    filename: str
    kind: Optional[str] = None
    size_bytes: int = 0
    mime: Optional[str] = None
    storage_key: Optional[str] = None
    source_url: Optional[str] = None
    sensitivity: Optional[str] = None
    linked_type: Optional[str] = None
    linked_id: Optional[str] = None


class MsgActionRequest(BaseModel):
    created_by: str
    title: str
    kind: str = "task"
    message_id: Optional[str] = None
    detail: Optional[str] = None
    owner_id: Optional[str] = None
    due_on: Optional[str] = None
    property_id: Optional[str] = None
    create_crm_task: bool = False


class MsgActionUpdateRequest(BaseModel):
    user_id: str
    status: Optional[str] = None
    owner_id: Optional[str] = None
    due_on: Optional[str] = None
    note: Optional[str] = None


class MsgActionCompleteRequest(BaseModel):
    user_id: str
    note: Optional[str] = None


class MsgDispatchRequest(BaseModel):
    user_id: Optional[str] = None
    limit: int = 200
    force: bool = False


class MsgTelegramLinkRequest(BaseModel):
    user_id: str
    chat_id: str
    username: Optional[str] = None
    categories: Optional[List[str]] = None


class MsgTelegramUpdateRequest(BaseModel):
    update: Dict[str, Any]


class MsgTelegramAlertRequest(BaseModel):
    user_id: str
    text: str
    priority: str = "normal"
    conversation_id: Optional[str] = None
    message_id: Optional[str] = None


class MsgPurgeRequest(BaseModel):
    dry_run: bool = True
    retention_days: Optional[int] = None
    actor_id: Optional[str] = None


class MsgReportRequest(BaseModel):
    message_id: str
    reporter_id: str
    reason: str = "other"
    detail: Optional[str] = None


class MsgModerateRequest(BaseModel):
    actor_id: str
    action: str
    note: Optional[str] = None


class MsgActionItemsRequest(BaseModel):
    user_id: str
    limit: int = 100
    create: bool = False
    owner_default: Optional[str] = None


# ---- Messaging: catalog & team directory ----

@app.get("/messaging/overview", tags=["messaging"])
def messaging_overview() -> Any:
    """Workspace config, channels, categories, counts and the rollout plan."""
    return j(core.msg_overview())


@app.get("/messaging/channels", tags=["messaging"])
def messaging_channels(channel_key: Optional[str] = None) -> Any:
    """Default team channels with purpose and access rules."""
    return j(core.msg_channels(channel_key))


@app.get("/messaging/channels/{channel_key}", tags=["messaging"])
def messaging_channel(channel_key: str) -> Any:
    """One team channel by key."""
    return j(core.msg_channels(channel_key))


@app.get("/messaging/categories", tags=["messaging"])
def messaging_categories(category: Optional[str] = None) -> Any:
    """Notification categories with delivery channels and urgency."""
    return j(core.msg_categories(category))


@app.get("/messaging/categories/{category}", tags=["messaging"])
def messaging_category(category: str) -> Any:
    """One notification category by key."""
    return j(core.msg_categories(category))


@app.get("/messaging/attachment-kinds", tags=["messaging"])
def messaging_attachment_kinds(kind: Optional[str] = None) -> Any:
    """Attachment kinds, accepted extensions and default sensitivity."""
    return j(core.msg_attachment_kinds(kind))


@app.get("/messaging/profiles", tags=["messaging"])
def messaging_profiles(presence: Optional[str] = None, role: Optional[str] = None,
                       query: Optional[str] = None) -> Any:
    """Team directory of messaging profiles."""
    return j(core.msg_profiles(presence=presence, role=role, query=query))


@app.post("/messaging/presence", tags=["messaging"])
def messaging_presence(payload: MsgPresenceRequest) -> Any:
    """Set a user's presence."""
    return j(core.msg_set_presence(payload.user_id, payload.presence))


@app.post("/messaging/presence/heartbeat", tags=["messaging"])
def messaging_heartbeat(payload: MsgPresenceRequest) -> Any:
    """Heartbeat a user's presence."""
    return j(core.msg_presence_heartbeat(payload.user_id, payload.presence))


@app.get("/messaging/preferences/{user_id}", tags=["messaging"])
def messaging_preferences(user_id: str) -> Any:
    """A user's notification preferences, quiet hours, digest and Telegram state."""
    return j(core.msg_preferences(user_id))


@app.put("/messaging/preferences/{user_id}", tags=["messaging"])
def messaging_set_preferences(user_id: str, payload: MsgPreferencesRequest) -> Any:
    """Update notification preferences."""
    data = payload.model_dump()
    return j(core.msg_set_preferences(
        user_id, prefs=data.get("prefs"), quiet_start=(data.get("quiet_hours") or {}).get("start"),
        quiet_end=(data.get("quiet_hours") or {}).get("end"), digest=data.get("digest"),
        telegram_opt_in=data.get("telegram_opt_in"),
        telegram_categories=data.get("telegram_categories")))


# ---- Messaging: conversations & members ----

@app.get("/messaging/conversations", tags=["messaging"])
def messaging_conversations(user_id: str, kind: Optional[str] = None,
                            include_archived: bool = False, property_id: Optional[str] = None,
                            channel_key: Optional[str] = None) -> Any:
    """List a user's conversations with unread counts."""
    return j(core.msg_conversations(user_id, kind=kind, include_archived=include_archived,
                                    property_id=property_id, channel_key=channel_key))


@app.post("/messaging/conversations", tags=["messaging"], status_code=201)
def messaging_create_conversation(payload: MsgConversationRequest) -> Any:
    """Create a direct / group / channel / property conversation."""
    return j(core.msg_create_conversation(**payload.model_dump()))


@app.get("/messaging/conversations/{conversation_id}", tags=["messaging"])
def messaging_conversation(conversation_id: str, user_id: str) -> Any:
    """One conversation with members, pins, unread count and context."""
    return j(core.msg_conversation(conversation_id, user_id))


@app.get("/messaging/conversations/{conversation_id}/context", tags=["messaging"])
def messaging_conversation_context(conversation_id: str, user_id: Optional[str] = None) -> Any:
    """What a conversation is tied to (property, pins, actions, attachments)."""
    return j(core.msg_conversation_context(conversation_id, user_id))


@app.post("/messaging/conversations/{conversation_id}/archive", tags=["messaging"])
def messaging_archive(conversation_id: str, payload: MsgArchiveRequest) -> Any:
    """Archive or restore a conversation."""
    return j(core.msg_archive_conversation(conversation_id, payload.user_id, payload.archived))


@app.get("/messaging/conversations/{conversation_id}/members", tags=["messaging"])
def messaging_members(conversation_id: str, user_id: Optional[str] = None) -> Any:
    """Members of a conversation."""
    return j(core.msg_members(conversation_id, user_id))


@app.post("/messaging/conversations/{conversation_id}/members", tags=["messaging"])
def messaging_add_member(conversation_id: str, payload: MsgMemberRequest) -> Any:
    """Add (or re-role) a member."""
    return j(core.msg_add_member(conversation_id, payload.member_id, actor_id=payload.actor_id,
                                 role=payload.role))


@app.put("/messaging/conversations/{conversation_id}/members/{member_id}", tags=["messaging"])
def messaging_update_member(conversation_id: str, member_id: str,
                            payload: MsgMemberUpdateRequest) -> Any:
    """Update a member's role, mute/pin state or notification level."""
    return j(core.msg_update_member(conversation_id, member_id, **payload.model_dump()))


@app.delete("/messaging/conversations/{conversation_id}/members/{member_id}", tags=["messaging"])
def messaging_remove_member(conversation_id: str, member_id: str,
                            actor_id: Optional[str] = None, reason: Optional[str] = None) -> Any:
    """Remove a member (audited access revocation)."""
    return j(core.msg_remove_member(conversation_id, member_id, actor_id=actor_id, reason=reason))


@app.post("/messaging/direct", tags=["messaging"])
def messaging_direct(payload: MsgDirectRequest) -> Any:
    """Find or create the 1-to-1 conversation between two users."""
    return j(core.msg_direct(payload.user_a, payload.user_b))


@app.post("/messaging/property-thread", tags=["messaging"])
def messaging_property_thread(payload: MsgPropertyThreadRequest) -> Any:
    """Get or create the internal discussion panel for a property."""
    return j(core.msg_property_thread(payload.property_id, created_by=payload.created_by,
                                      title=payload.title))


@app.post("/messaging/revoke-access", tags=["messaging"])
def messaging_revoke_access(payload: MsgRevokeRequest) -> Any:
    """Revoke a user's access to every conversation and unlink Telegram."""
    return j(core.msg_revoke_access(payload.user_id, actor_id=payload.actor_id, reason=payload.reason))


# ---- Messaging: messages ----

@app.get("/messaging/conversations/{conversation_id}/messages", tags=["messaging"])
def messaging_messages(conversation_id: str, user_id: str, limit: int = 50,
                       before_seq: Optional[int] = None, thread_id: Optional[str] = None,
                       include_deleted: bool = False) -> Any:
    """Page through a conversation's messages (or one thread)."""
    return j(core.msg_messages(conversation_id, user_id, limit=limit, before_seq=before_seq,
                               thread_id=thread_id, include_deleted=include_deleted))


@app.post("/messaging/conversations/{conversation_id}/messages", tags=["messaging"],
          status_code=201)
def messaging_post(conversation_id: str, payload: MsgPostRequest) -> Any:
    """Post a message."""
    return j(core.msg_post(conversation_id, **payload.model_dump()))


@app.post("/messaging/conversations/{conversation_id}/read", tags=["messaging"])
def messaging_mark_read(conversation_id: str, payload: MsgReadRequest) -> Any:
    """Mark a conversation read up to a sequence number."""
    return j(core.msg_mark_read(conversation_id, payload.user_id, payload.up_to_seq))


@app.get("/messaging/messages/{message_id}", tags=["messaging"])
def messaging_message(message_id: str, user_id: str) -> Any:
    """One message with attachments, reactions, receipts and replies."""
    return j(core.msg_message(message_id, user_id))


@app.put("/messaging/messages/{message_id}", tags=["messaging"])
def messaging_edit_message(message_id: str, payload: MsgEditRequest) -> Any:
    """Edit a message (author only, within the edit window)."""
    return j(core.msg_edit_message(message_id, payload.user_id, payload.body))


@app.delete("/messaging/messages/{message_id}", tags=["messaging"])
def messaging_delete_message(message_id: str, user_id: str, reason: Optional[str] = None) -> Any:
    """Soft-delete a message."""
    return j(core.msg_delete_message(message_id, user_id, reason))


@app.post("/messaging/messages/{message_id}/pin", tags=["messaging"])
def messaging_pin_message(message_id: str, payload: MsgPinRequest) -> Any:
    """Pin or unpin a message."""
    return j(core.msg_pin_message(message_id, payload.user_id, payload.pinned))


@app.post("/messaging/messages/{message_id}/react", tags=["messaging"])
def messaging_react(message_id: str, payload: MsgReactRequest) -> Any:
    """Toggle an emoji reaction."""
    return j(core.msg_react(message_id, payload.user_id, payload.emoji))


@app.get("/messaging/messages/{message_id}/thread", tags=["messaging"])
def messaging_thread(message_id: str, user_id: str, limit: int = 100) -> Any:
    """Threaded replies to a message."""
    return j(core.msg_thread(message_id, user_id, limit))


@app.get("/messaging/messages/{message_id}/receipts", tags=["messaging"])
def messaging_receipts(message_id: str, user_id: str) -> Any:
    """Read receipts for a message."""
    return j(core.msg_read_receipts(message_id, user_id))


@app.get("/messaging/search", tags=["messaging"])
def messaging_search(user_id: str, query: str = "", conversation_id: Optional[str] = None,
                     property_id: Optional[str] = None, mention: Optional[str] = None,
                     limit: int = 25) -> Any:
    """Search messages across every conversation the user may access."""
    return j(core.msg_search(user_id, query, conversation_id=conversation_id,
                             property_id=property_id, mention=mention, limit=limit))


@app.get("/messaging/unread/{user_id}", tags=["messaging"])
def messaging_unread(user_id: str) -> Any:
    """Unread totals overall and per conversation."""
    return j(core.msg_unread(user_id))


@app.get("/messaging/conversations/{conversation_id}/summary", tags=["messaging"])
def messaging_summary(conversation_id: str, user_id: str, limit: int = 80) -> Any:
    """Rules-based extractive summary of a conversation."""
    return j(core.msg_summarize(conversation_id, user_id, limit))


@app.get("/messaging/conversations/{conversation_id}/digest", tags=["messaging"])
def messaging_digest(conversation_id: str, user_id: str, days: int = 7) -> Any:
    """Recent-activity digest for a conversation."""
    return j(core.msg_conversation_digest(conversation_id, user_id, days))


@app.post("/messaging/conversations/{conversation_id}/action-items", tags=["messaging"])
def messaging_action_items(conversation_id: str, payload: MsgActionItemsRequest) -> Any:
    """Extract (and optionally create) action items from a conversation."""
    return j(core.msg_action_items(conversation_id, payload.user_id, limit=payload.limit,
                                   create=payload.create, owner_default=payload.owner_default))


# ---- Messaging: attachments & expiring links ----

@app.get("/messaging/conversations/{conversation_id}/attachments", tags=["messaging"])
def messaging_attachments(conversation_id: str, user_id: str, kind: Optional[str] = None,
                          sensitivity: Optional[str] = None) -> Any:
    """List a conversation's shared files (references, never embedded content)."""
    return j(core.msg_attachments(conversation_id, user_id, kind=kind, sensitivity=sensitivity))


@app.post("/messaging/conversations/{conversation_id}/attachments", tags=["messaging"],
          status_code=201)
def messaging_attach(conversation_id: str, payload: MsgAttachmentRequest) -> Any:
    """Register a file reference for sharing."""
    return j(core.msg_attach(conversation_id, **payload.model_dump()))


@app.get("/messaging/attachments/{attachment_id}/link", tags=["messaging"])
def messaging_attachment_link(attachment_id: str, user_id: str,
                              ttl_minutes: Optional[int] = None) -> Any:
    """Mint a signed, expiring, permission-checked download link."""
    return j(core.msg_attachment_link(attachment_id, user_id, ttl_minutes))


@app.get("/messaging/attachments/{attachment_id}", tags=["messaging"])
def messaging_attachment_download(attachment_id: str, token: Optional[str] = None,
                                  user_id: Optional[str] = None) -> Any:
    """Resolve an attachment through a signed token (re-checks membership + expiry)."""
    if not token:
        raise HTTPException(status_code=400, detail="a signed ?token= is required")
    return j(core.msg_attachment_resolve(token, user_id))


@app.get("/messaging/attachments/resolve/{token}", tags=["messaging"])
def messaging_attachment_resolve(token: str, user_id: Optional[str] = None) -> Any:
    """Verify a signed attachment link and return the file reference."""
    return j(core.msg_attachment_resolve(token, user_id))


# ---- Messaging: actions (message -> task / approval / verification) ----

@app.get("/messaging/conversations/{conversation_id}/actions", tags=["messaging"])
def messaging_conversation_actions(conversation_id: str, user_id: str,
                                   status: Optional[str] = None) -> Any:
    """Actions raised inside a conversation."""
    return j(core.msg_actions(user_id, conversation_id=conversation_id, status=status))


@app.post("/messaging/conversations/{conversation_id}/actions", tags=["messaging"],
          status_code=201)
def messaging_create_action(conversation_id: str, payload: MsgActionRequest) -> Any:
    """Turn a message (or conversation) into a tracked action."""
    return j(core.msg_create_action(conversation_id, **payload.model_dump()))


@app.get("/messaging/actions", tags=["messaging"])
def messaging_actions(user_id: str, conversation_id: Optional[str] = None,
                      owner_id: Optional[str] = None, status: Optional[str] = None,
                      kind: Optional[str] = None, overdue_only: bool = False) -> Any:
    """List tracked actions."""
    return j(core.msg_actions(user_id, conversation_id=conversation_id, owner_id=owner_id,
                              status=status, kind=kind, overdue_only=overdue_only))


@app.get("/messaging/actions/{action_id}", tags=["messaging"])
def messaging_action(action_id: str, user_id: str) -> Any:
    """One tracked action."""
    return j(core.msg_action(action_id, user_id))


@app.put("/messaging/actions/{action_id}", tags=["messaging"])
def messaging_update_action(action_id: str, payload: MsgActionUpdateRequest) -> Any:
    """Update an action's status, owner or due date."""
    return j(core.msg_update_action(action_id, **payload.model_dump()))


@app.post("/messaging/actions/{action_id}/complete", tags=["messaging"])
def messaging_complete_action(action_id: str, payload: MsgActionCompleteRequest) -> Any:
    """Mark an action done and notify its creator."""
    return j(core.msg_complete_action(action_id, payload.user_id, payload.note))


# ---- Messaging: notifications, outbox & dispatch ----

@app.get("/messaging/notifications/{user_id}", tags=["messaging"])
def messaging_notifications(user_id: str, unread_only: bool = False,
                            category: Optional[str] = None, limit: int = 50) -> Any:
    """A user's notifications with unread count."""
    return j(core.msg_notifications(user_id, unread_only=unread_only, category=category,
                                    limit=limit))


@app.post("/messaging/notifications/{notification_id}/read", tags=["messaging"])
def messaging_read_notification(notification_id: str, user_id: str) -> Any:
    """Mark one notification read."""
    return j(core.msg_read_notification(notification_id, user_id))


@app.post("/messaging/notifications/{user_id}/read-all", tags=["messaging"])
def messaging_read_all(user_id: str) -> Any:
    """Mark every notification read for a user."""
    return j(core.msg_mark_all_notifications_read(user_id))


@app.post("/messaging/dispatch", tags=["messaging"])
def messaging_dispatch(payload: Optional[MsgDispatchRequest] = None) -> Any:
    """Drain the notification queue into the outbox (background-worker seam)."""
    data = (payload or MsgDispatchRequest()).model_dump()
    return j(core.msg_dispatch(**data))


@app.get("/messaging/outbox", tags=["messaging"])
def messaging_outbox(channel: Optional[str] = None, user_id: Optional[str] = None,
                     limit: int = 100) -> Any:
    """Delivered notifications with rendered e-mail/Telegram payloads."""
    return j(core.msg_outbox(channel=channel, user_id=user_id, limit=limit))


@app.get("/messaging/unread-summary/{user_id}", tags=["messaging"])
def messaging_unread_summary(user_id: str) -> Any:
    """Combined unread picture for a user."""
    return j(core.msg_unread_summary(user_id))


# ---- Messaging: Telegram (optional alert channel) ----

@app.post("/messaging/telegram/link-code", tags=["messaging"])
def messaging_telegram_link_code(user_id: str) -> Any:
    """Mint a single-use /start code for linking a Telegram chat."""
    return j(core.msg_telegram_link_code(user_id))


@app.post("/messaging/telegram/link", tags=["messaging"])
def messaging_telegram_link(payload: MsgTelegramLinkRequest) -> Any:
    """Opt a user in: bind a Telegram chat id and allowed categories."""
    return j(core.msg_telegram_link(**payload.model_dump()))


@app.post("/messaging/telegram/unlink", tags=["messaging"])
def messaging_telegram_unlink(user_id: str) -> Any:
    """Unlink a user's Telegram chat."""
    return j(core.msg_telegram_unlink(user_id))


@app.get("/messaging/telegram/links", tags=["messaging"])
def messaging_telegram_links(active_only: bool = True) -> Any:
    """Every Telegram link."""
    return j(core.msg_telegram_links(active_only))


@app.get("/messaging/telegram/status/{user_id}", tags=["messaging"])
def messaging_telegram_status(user_id: str) -> Any:
    """WhatsApp-style status for the Telegram channel (link state and categories)."""
    return j(core.msg_telegram_status(user_id))


@app.post("/messaging/telegram/update", tags=["messaging"])
def messaging_telegram_update(payload: MsgTelegramUpdateRequest,
                              x_telegram_bot_api_secret_token: Optional[str] = Header(default=None)) -> Any:
    """Process one inbound Telegram bot update. When ``PORTAL_TELEGRAM_WEBHOOK_SECRET`` is set (the
    ``secret_token`` given to Telegram's setWebhook), Telegram's header must carry it."""
    secret = os.getenv("PORTAL_TELEGRAM_WEBHOOK_SECRET", "").strip()
    if secret and not hmac.compare_digest((x_telegram_bot_api_secret_token or "").encode(), secret.encode()):
        raise HTTPException(status_code=401, detail="Bad secret token")
    return j(core.msg_telegram_update(payload.update))


@app.post("/messaging/telegram/alert", tags=["messaging"])
def messaging_telegram_alert(payload: MsgTelegramAlertRequest) -> Any:
    """Queue and dispatch a sanitised Telegram alert."""
    return j(core.msg_telegram_alert(**payload.model_dump()))


# ---- Messaging: audit, retention, moderation & statistics ----

@app.get("/messaging/audit", tags=["messaging"])
def messaging_audit(limit: int = 100, action: Optional[str] = None,
                    actor_id: Optional[str] = None, target_type: Optional[str] = None) -> Any:
    """The messaging audit trail."""
    return j(core.msg_audit(limit=limit, action=action, actor_id=actor_id, target_type=target_type))


@app.get("/messaging/retention", tags=["messaging"])
def messaging_retention() -> Any:
    """Per-conversation retention picture."""
    return j(core.msg_retention_report())


@app.post("/messaging/purge", tags=["messaging"])
def messaging_purge(payload: MsgPurgeRequest) -> Any:
    """Apply the retention policy (soft-delete past the window; pinned exempt)."""
    return j(core.msg_purge_retention(**payload.model_dump()))


@app.get("/messaging/reports", tags=["messaging"])
def messaging_reports(status: Optional[str] = None, limit: int = 100) -> Any:
    """Message reports and their moderation status."""
    return j(core.msg_reports(status=status, limit=limit))


@app.post("/messaging/reports", tags=["messaging"], status_code=201)
def messaging_report(payload: MsgReportRequest) -> Any:
    """Report a message (spam, abuse, confidential leak, off-topic)."""
    return j(core.msg_report_message(**payload.model_dump()))


@app.post("/messaging/reports/{report_id}/moderate", tags=["messaging"])
def messaging_moderate(report_id: str, payload: MsgModerateRequest) -> Any:
    """Resolve a report: dismiss, delete, mute the author or escalate."""
    return j(core.msg_moderate_report(report_id, **payload.model_dump()))


@app.get("/messaging/statistics", tags=["messaging"])
def messaging_statistics() -> Any:
    """Aggregate messaging statistics."""
    return j(core.msg_statistics())


@app.get("/messaging/portal", tags=["messaging"], response_class=HTMLResponse)
def messaging_portal(lang: str = Depends(ui_lang), theme: str = Depends(ui_theme)) -> HTMLResponse:
    """The Team Messaging & Notifications page (HTML)."""
    return HTMLResponse(content=core.messaging_portal_html(lang=lang, theme=theme))


@app.get("/messaging/portal.html", tags=["messaging"], response_class=HTMLResponse)
def messaging_portal_html(lang: str = Depends(ui_lang), theme: str = Depends(ui_theme)) -> HTMLResponse:
    """Alias of ``/messaging/portal`` that always serves HTML."""
    return HTMLResponse(content=core.messaging_portal_html(lang=lang, theme=theme))


# ---- Messaging: real-time feed (WebSocket) ----

@app.websocket("/ws/messaging/{conversation_id}")
async def messaging_socket(websocket: WebSocket, conversation_id: str,
                           user_id: Optional[str] = None, token: Optional[str] = None) -> None:
    """Live conversation feed: new messages, edits, reactions, actions and read state.

    The caller passes ``?token=`` (its sign-in token; browsers can't set headers on a WebSocket)
    and ``?user_id=``, which must be the signed-in user; access is re-checked on every connection.
    """
    me = _resolve_user(token)
    if me is None or (user_id and user_id != me["id"] and not access.is_admin(me)):
        await websocket.close(code=4401)
        return
    user_id = user_id or me["id"]
    conv = core.messaging._get(core.messaging.conversations_db, "id", conversation_id)
    if conv is None or not core.messaging.can_access(conv, user_id):
        await websocket.close(code=4403)
        return
    await websocket.accept()
    listener = core.messaging.subscribe(conversation_id)

    async def pump() -> None:
        while True:
            try:
                event = listener.get_nowait()
            except Exception:
                event = None
            if event is not None:
                await websocket.send_json(event)
            await asyncio.sleep(0.3)

    pump_task = asyncio.create_task(pump())
    try:
        await websocket.send_json({"event": "ready", "conversation_id": conversation_id,
                                   "user_id": user_id})
        while True:
            text = await websocket.receive_text()
            if text == "ping":
                await websocket.send_json({"event": "pong"})
            elif text == "unread":
                await websocket.send_json({"event": "unread",
                                           "unread": core.messaging.unread_counts(user_id)})
    except WebSocketDisconnect:
        pass
    finally:
        pump_task.cancel()
        core.messaging.unsubscribe(conversation_id, listener)


__all__ = ["app"]
