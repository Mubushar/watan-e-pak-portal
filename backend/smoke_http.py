"""
Live HTTP smoke test (uses the real uvicorn server, not TestClient).

Starts the combined app on 127.0.0.1:8011, then checks:
  * REST  : /health, /properties, /crm/dashboard
  * MCP   : POST /mcp 'initialize' handshake over Streamable HTTP

Run:
    uv run python smoke_http.py
"""

import logging
import threading
import time

import httpx
import uvicorn

from api import app

for _name in ("httpx", "httpcore", "mcp", "uvicorn", "anyio", "asyncio"):
    logging.getLogger(_name).setLevel(logging.WARNING)
logging.getLogger().setLevel(logging.WARNING)

PORT = 8011


def main() -> None:
    config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    for _ in range(100):
        if server.started:
            break
        time.sleep(0.1)

    base = f"http://127.0.0.1:{PORT}"
    ok = True

    scheme_id = __import__("server").housing_schemes_db[0].id

    r = httpx.get(f"{base}/health")
    print("REST /health        ->", r.status_code, r.json())
    ok &= r.status_code == 200

    r = httpx.get(f"{base}/properties")
    print("REST /properties    ->", r.status_code, "count =", r.json()["count"])
    ok &= r.status_code == 200

    r = httpx.get(f"{base}/crm/dashboard")
    print("REST /crm/dashboard ->", r.status_code, "leads =", r.json()["leads"]["total"])
    ok &= r.status_code == 200

    r = httpx.get(f"{base}/v1/models")
    print("OPENAI /v1/models    ->", r.status_code, [m["id"] for m in r.json().get("data", [])])
    ok &= r.status_code == 200

    r = httpx.get(f"{base}/gis/base-maps")
    print("REST /gis/base-maps ->", r.status_code, "base maps =", r.json().get("count"))
    ok &= r.status_code == 200 and r.json().get("count", 0) >= 5

    r = httpx.get(f"{base}/gis/master-plans")
    print("REST /gis/master-plans ->", r.status_code, "master plans =", r.json().get("count"))
    ok &= r.status_code == 200 and r.json().get("count", 0) > 0

    r = httpx.get(f"{base}/gis/properties-in-bounds",
                  params={"south": 31.40, "west": 74.20, "north": 31.55, "east": 74.40})
    print("REST /gis/properties-in-bounds ->", r.status_code, "hits =", r.json().get("count"))
    ok &= r.status_code == 200 and r.json().get("count", 0) > 0

    r = httpx.get(f"{base}/gis/export/kml/scheme/{scheme_id}")
    print("REST /gis/export/kml ->", r.status_code, r.headers.get("content-type"))
    ok &= r.status_code == 200 and "<kml" in r.text

    r = httpx.get(f"{base}/gis/map/scheme/{scheme_id}")
    print("REST /gis/map        ->", r.status_code, "html chars =", len(r.text))
    ok &= r.status_code == 200 and "leaflet" in r.text.lower()

    r = httpx.get(f"{base}/gis/analysis/scheme/{scheme_id}")
    an = r.json() if r.status_code == 200 else {}
    print("REST /gis/analysis   ->", r.status_code, "dev cost =", an.get("development_cost", {}).get("total"),
          "jobs =", an.get("economic_impact", {}).get("jobs_total"))
    ok &= r.status_code == 200 and an.get("development_cost", {}).get("total", 0) > 0

    r = httpx.get(f"{base}/gis/ring-analysis", params={"lat": 31.4504, "lon": 74.28, "radii_km": "1,3,5"})
    print("REST /gis/ring-analysis ->", r.status_code, "rings =", len(r.json().get("rings", [])))
    ok &= r.status_code == 200 and len(r.json().get("rings", [])) == 3

    r = httpx.get(f"{base}/gis/report/scheme/{scheme_id}")
    print("REST /gis/report     ->", r.status_code, "html chars =", len(r.text))
    ok &= r.status_code == 200 and "Economic impact" in r.text

    r = httpx.get(f"{base}/gis/outlook/scheme/{scheme_id}")
    print("REST /gis/outlook    ->", r.status_code, "html chars =", len(r.text),
          "ticker =", "portal-ticker" in r.text)
    ok &= r.status_code == 200 and "portal-ticker" in r.text

    r = httpx.get(f"{base}/gis/analysis/scheme/{scheme_id}/forecast", params={"years": 5})
    fc = r.json().get("forecast", {}) if r.status_code == 200 else {}
    print("REST /gis/.../forecast ->", r.status_code, "index =", fc.get("composite_index"),
          "band =", fc.get("index_band"), "base CAGR =", fc.get("base_cagr"))
    ok &= r.status_code == 200 and fc.get("composite_index", 0) > 0

    r = httpx.get(f"{base}/news/channels")
    print("REST /news/channels  ->", r.status_code, "channels =", r.json().get("count"))
    ok &= r.status_code == 200

    r = httpx.get(f"{base}/news/ticker.html", params={"city": "Lahore"})
    print("REST /news/ticker.html ->", r.status_code, "ticker =", "portal-ticker" in r.text)
    ok &= r.status_code == 200 and "portal-ticker" in r.text

    # --- auth: OTP signup -> verify -> protected call ---
    r = httpx.post(f"{base}/auth/signup", json={
        "email": "smoke@portal.test", "mobile": "0347 777 0101",
        "password": "Secret@123", "name": "Smoke User",
    })
    dev = ((r.json().get("verification") or {}).get("dev_otp") or {}) if r.status_code == 201 else {}
    print("REST /auth/signup     ->", r.status_code, "otp channels =", list(dev))
    ok &= r.status_code == 201 and len(dev) == 2

    r = httpx.post(f"{base}/auth/verify-otp", json={"identifier": "smoke@portal.test", "code": dev.get("smoke@portal.test")})
    token = r.json().get("token") if r.status_code == 200 else None
    print("REST /auth/verify-otp ->", r.status_code, "token =", bool(token))
    ok &= r.status_code == 200 and bool(token)

    r = httpx.get(f"{base}/auth/me", headers={"Authorization": f"Bearer {token}"})
    print("REST /auth/me         ->", r.status_code, "user =", (r.json().get("user") or {}).get("status"))
    ok &= r.status_code == 200 and r.json()["user"]["email"] == "smoke@portal.test"

    r = httpx.get(f"{base}/auth/me")
    print("REST /auth/me (no tok)->", r.status_code)
    ok &= r.status_code == 401

    r = httpx.post(f"{base}/auth/login", json={"identifier": "smoke@portal.test", "password": "Secret@123"})
    print("REST /auth/login      ->", r.status_code)
    ok &= r.status_code == 200

    # --- dual-language + light/dark theme ---
    r = httpx.get(f"{base}/gis/outlook/scheme/{scheme_id}", params={"lang": "ur", "theme": "dark"})
    print("REST /gis/outlook ur/dark ->", r.status_code, "rtl =", 'dir="rtl"' in r.text,
          "dark =", 'html[data-theme="dark"]' in r.text)
    ok &= r.status_code == 200 and 'dir="rtl"' in r.text and 'html[data-theme="dark"]' in r.text

    r = httpx.get(f"{base}/gis/report/scheme/{scheme_id}", headers={"Accept-Language": "ur"})
    print("REST /gis/report (Accept-Language ur) ->", r.status_code, "rtl =", 'dir="rtl"' in r.text)
    ok &= r.status_code == 200 and 'dir="rtl"' in r.text

    r = httpx.get(f"{base}/news/ticker", params={"city": "Lahore", "lang": "ur"})
    print("REST /news/ticker ur ->", r.status_code, "rtl =", 'dir="rtl"' in r.text)
    ok &= r.status_code == 200 and "رئیل اسٹیٹ خبریں" in r.text

    r = httpx.get(f"{base}/i18n/languages")
    print("REST /i18n/languages  ->", r.status_code, [x["code"] for x in r.json().get("languages", [])])
    ok &= r.status_code == 200 and len(r.json().get("languages", [])) == 2

    r = httpx.get(f"{base}/ui/themes")
    print("REST /ui/themes       ->", r.status_code, [x["code"] for x in r.json().get("themes", [])])
    ok &= r.status_code == 200 and len(r.json().get("themes", [])) == 3

    # --- accounting + finance (ROI) ---
    r = httpx.get(f"{base}/accounting/info")
    print("REST /accounting/info ->", r.status_code, "accounts =", r.json().get("counts", {}).get("accounts"))
    ok &= r.status_code == 200 and r.json().get("counts", {}).get("accounts", 0) > 30

    r = httpx.get(f"{base}/accounting/trial-balance")
    print("REST /accounting/trial-balance ->", r.status_code, "balanced =", r.json().get("balanced"))
    ok &= r.status_code == 200 and r.json().get("balanced") is True

    r = httpx.get(f"{base}/accounting/dashboard")
    print("REST /accounting/dashboard ->", r.status_code, "assets =", r.json().get("total_assets"),
          "profit =", r.json().get("net_profit"))
    ok &= r.status_code == 200 and r.json().get("total_assets", 0) > 0

    r = httpx.get(f"{base}/accounting/rent-roll")
    print("REST /accounting/rent-roll ->", r.status_code, "monthly rent =", r.json().get("monthly_rent"))
    ok &= r.status_code == 200 and r.json().get("monthly_rent", 0) > 0

    r = httpx.post(f"{base}/finance/investment-metrics",
                   json={"cashflows": [-10_000_000, 3_000_000, 4_000_000, 5_000_000, 4_000_000]})
    print("REST /finance/investment-metrics ->", r.status_code, "irr =", r.json().get("irr"),
          "npv =", r.json().get("npv"))
    ok &= r.status_code == 200 and r.json().get("irr") is not None

    r = httpx.get(f"{base}/finance/mortgage", params={"principal": 8_000_000})
    print("REST /finance/mortgage ->", r.status_code, "payment =", r.json().get("payment"))
    ok &= r.status_code == 200 and r.json().get("payment", 0) > 0

    r = httpx.get(f"{base}/finance/portfolio-roi")
    print("REST /finance/portfolio-roi ->", r.status_code, "value =", r.json().get("market_value"))
    ok &= r.status_code == 200 and r.json().get("market_value", 0) > 0

    # --- POI + AOI ---
    r = httpx.get(f"{base}/poi/categories")
    print("REST /poi/categories ->", r.status_code, "pois =", r.json().get("count"))
    ok &= r.status_code == 200 and r.json().get("count", 0) > 0

    r = httpx.get(f"{base}/poi/nearby", params={"latitude": 31.4504, "longitude": 74.2810, "radius_km": 3})
    print("REST /poi/nearby ->", r.status_code, "hits =", r.json().get("count"))
    ok &= r.status_code == 200 and r.json().get("count", 0) > 0

    r = httpx.get(f"{base}/poi/map", params={"entity_type": "scheme", "entity_id": scheme_id})
    print("REST /poi/map ->", r.status_code, "html chars =", len(r.text))
    ok &= r.status_code == 200 and "leaflet" in r.text.lower()

    r = httpx.get(f"{base}/aoi")
    aois = r.json().get("areas", []) if r.status_code == 200 else []
    print("REST /aoi ->", r.status_code, "aois =", len(aois))
    ok &= r.status_code == 200 and len(aois) > 0

    if aois:
        aoi_id = aois[0]["id"]
        r = httpx.get(f"{base}/aoi/{aoi_id}/analyze")
        print("REST /aoi/{id}/analyze ->", r.status_code,
              "index =", r.json().get("forecast", {}).get("composite_index"))
        ok &= r.status_code == 200 and r.json().get("forecast", {}).get("composite_index", 0) > 0

        r = httpx.get(f"{base}/aoi/{aoi_id}/report", params={"lang": "ur", "theme": "dark"})
        print("REST /aoi/{id}/report ur/dark ->", r.status_code, "rtl =", 'dir="rtl"' in r.text)
        ok &= r.status_code == 200 and 'dir="rtl"' in r.text

    # --- portal discovery / analytics ---
    r = httpx.get(f"{base}/portal/health")
    print("REST /portal/health ->", r.status_code, "tools =", r.json().get("mcp", {}).get("tools"))
    ok &= r.status_code == 200 and r.json().get("mcp", {}).get("tools", 0) > 200

    r = httpx.get(f"{base}/portal/catalog")
    print("REST /portal/catalog ->", r.status_code, "groups =", len(r.json().get("groups", {})))
    ok &= r.status_code == 200 and r.json().get("tool_count", 0) > 200

    r = httpx.get(f"{base}/portal/statistics")
    print("REST /portal/statistics ->", r.status_code, "properties =",
          r.json().get("inventory", {}).get("properties"))
    ok &= r.status_code == 200 and r.json().get("inventory", {}).get("properties", 0) > 0

    r = httpx.get(f"{base}/portal/search", params={"query": "lahore"})
    print("REST /portal/search ->", r.status_code, "total =", r.json().get("total"))
    ok &= r.status_code == 200 and r.json().get("total", 0) > 0

    r = httpx.get(f"{base}/portal/market-trends", params={"city": "Lahore"})
    print("REST /portal/market-trends ->", r.status_code,
          "cagr =", r.json().get("forecast", {}).get("base_cagr"))
    ok &= r.status_code == 200 and r.json().get("forecast", {}).get("base_cagr", 0) > 0

    # --- portal content + advertising + users/roles + routing ---
    r = httpx.get(f"{base}/content/overview")
    print("REST /content/overview ->", r.status_code, "counts =", r.json().get("counts"))
    ok &= r.status_code == 200 and r.json().get("counts", {}).get("pages", 0) > 0

    r = httpx.get(f"{base}/content/pages/about")
    print("REST /content/pages/about ->", r.status_code, "key =", r.json().get("key"))
    ok &= r.status_code == 200 and r.json().get("key") == "about"

    r = httpx.get(f"{base}/content/site", params={"lang": "ur"})
    print("REST /content/site ur ->", r.status_code, "blocks =", len(r.json().get("layout", [])))
    ok &= r.status_code == 200 and len(r.json().get("layout", [])) > 0

    r = httpx.get(f"{base}/portal/home", params={"lang": "ur", "theme": "dark"})
    print("REST /portal/home ur/dark ->", r.status_code, "rtl =", 'dir="rtl"' in r.text,
          "ads =", "ad-section" in r.text)
    ok &= r.status_code == 200 and 'dir="rtl"' in r.text and "ad-section" in r.text

    r = httpx.get(f"{base}/ads/active", params={"slot": "hero"})
    print("REST /ads/active hero ->", r.status_code, "live =", r.json().get("count"))
    ok &= r.status_code == 200 and r.json().get("count", 0) > 0

    r = httpx.get(f"{base}/ads/performance")
    print("REST /ads/performance ->", r.status_code, "ads =", r.json().get("totals", {}).get("ads"),
          "ctr =", r.json().get("totals", {}).get("ctr"))
    ok &= r.status_code == 200 and r.json().get("totals", {}).get("ads", 0) > 0

    r = httpx.get(f"{base}/ads/report")
    print("REST /ads/report ->", r.status_code, "html chars =", len(r.text))
    ok &= r.status_code == 200 and "ad-section" in r.text

    r = httpx.get(f"{base}/roles/summary")
    print("REST /roles/summary ->", r.status_code, "roles =", r.json().get("roles"),
          "permissions =", r.json().get("permissions"))
    ok &= r.status_code == 200 and r.json().get("roles", 0) > 0

    r = httpx.get(f"{base}/roles/agent/users")
    print("REST /roles/agent/users ->", r.status_code, "users =", r.json().get("count"))
    ok &= r.status_code == 200 and r.json().get("count", 0) > 0

    r = httpx.get(f"{base}/gis/travel-modes")
    print("REST /gis/travel-modes ->", r.status_code, "modes =", [m["mode"] for m in r.json().get("modes", [])])
    ok &= r.status_code == 200 and len(r.json().get("modes", [])) >= 3

    route_params = {"origin_latitude": 31.4504, "origin_longitude": 74.2810,
                    "destination_latitude": 31.4690, "destination_longitude": 74.4120, "mode": "drive"}
    r = httpx.get(f"{base}/gis/route", params=route_params)
    best = r.json().get("best", {}) if r.status_code == 200 else {}
    print("REST /gis/route drive ->", r.status_code, "km =", best.get("distance_km"),
          "eta =", best.get("duration_text"), "alts =", r.json().get("alternative_count"))
    ok &= r.status_code == 200 and best.get("distance_m", 0) > 0

    r = httpx.get(f"{base}/gis/route/compare", params={k: v for k, v in route_params.items() if k != "mode"})
    print("REST /gis/route/compare ->", r.status_code, "modes =", list(r.json().get("modes", {})))
    ok &= r.status_code == 200 and {"walk", "drive"} <= set(r.json().get("modes", {}))

    r = httpx.get(f"{base}/poi/route", params={"origin_poi": "Smart City Public School",
                                               "destination_poi": "Downtown Shopping Mall", "mode": "walk"})
    print("REST /poi/route walk ->", r.status_code, "km =", r.json().get("best", {}).get("distance_km"),
          "eta =", r.json().get("best", {}).get("duration_text"))
    ok &= r.status_code == 200 and r.json().get("mode") == "walk"

    r = httpx.get(f"{base}/gis/route/map", params=route_params)
    print("REST /gis/route/map ->", r.status_code, "html chars =", len(r.text))
    ok &= r.status_code == 200 and "leaflet" in r.text.lower()

    # --- construction wing ---
    r = httpx.get(f"{base}/construction/overview")
    print("REST /construction/overview ->", r.status_code, "systems =",
          r.json().get("counts", {}).get("systems"), "materials =", r.json().get("counts", {}).get("materials"))
    ok &= r.status_code == 200 and r.json().get("counts", {}).get("systems", 0) >= 10

    r = httpx.post(f"{base}/construction/estimate", json={"covered_area": 2722.5, "floors": 2,
                                                          "quality_tier": "standard"})
    print("REST /construction/estimate ->", r.status_code, "total =",
          r.json().get("cost", {}).get("total_text"), "per sqft =", r.json().get("cost", {}).get("cost_per_sqft"))
    ok &= r.status_code == 200 and r.json().get("cost", {}).get("total", 0) > 0

    r = httpx.get(f"{base}/construction/compare", params={"covered_area": 2722.5})
    print("REST /construction/compare ->", r.status_code, "options =", r.json().get("count"),
          "cheapest =", r.json().get("cheapest"))
    ok &= r.status_code == 200 and r.json().get("count", 0) >= 3

    r = httpx.get(f"{base}/construction/portal", params={"lang": "en"})
    print("REST /construction/portal ->", r.status_code, "html chars =", len(r.text))
    ok &= r.status_code == 200 and "Construction wing" in r.text

    r = httpx.post(f"{base}/construction/report", json={"covered_area": 2000})
    print("REST /construction/report ->", r.status_code, "html chars =", len(r.text))
    ok &= r.status_code == 200 and "Element build-up" in r.text

    # --- maintenance wing ---
    r = httpx.get(f"{base}/maintenance/overview")
    print("REST /maintenance/overview ->", r.status_code, "components =",
          r.json().get("counts", {}).get("components"), "defects =", r.json().get("counts", {}).get("defects"))
    ok &= r.status_code == 200 and r.json().get("counts", {}).get("components", 0) >= 10

    r = httpx.get(f"{base}/maintenance/estimate", params={"covered_area": 2000, "age_years": 8})
    print("REST /maintenance/estimate ->", r.status_code, "annual =",
          r.json().get("annual", {}).get("total_text"), "reserve =",
          r.json().get("reserve", {}).get("annual_reserve"))
    ok &= r.status_code == 200 and r.json().get("annual", {}).get("total", 0) > 0

    r = httpx.get(f"{base}/maintenance/lifecycle", params={"covered_area": 4000, "property_type": "apartment"})
    print("REST /maintenance/lifecycle ->", r.status_code, "replacements =",
          len(r.json().get("replacements", [])), "annualised =", r.json().get("annualised"))
    ok &= r.status_code == 200 and r.json().get("total_replacement_cost", 0) > 0

    r = httpx.get(f"{base}/maintenance/portal", params={"lang": "ur", "theme": "dark"})
    print("REST /maintenance/portal ur/dark ->", r.status_code, "rtl =", 'dir="rtl"' in r.text,
          "html chars =", len(r.text))
    ok &= r.status_code == 200 and "دیکھ بھال" in r.text

    r = httpx.post(f"{base}/maintenance/report", json={"covered_area": 2000, "property_type": "apartment"})
    print("REST /maintenance/report ->", r.status_code, "html chars =", len(r.text))
    ok &= r.status_code == 200 and "Maintenance summary" in r.text

    # --- agentic OS / transactions / intelligence / leasing / marketing / commercial ---
    r = httpx.get(f"{base}/agents/overview")
    print("REST /agents/overview ->", r.status_code, "agents =", r.json().get("counts", {}).get("agents"),
          "products =", r.json().get("counts", {}).get("products"))
    ok &= r.status_code == 200 and r.json().get("counts", {}).get("products") == 8

    r = httpx.get(f"{base}/agents/smart-actions")
    print("REST /agents/smart-actions ->", r.status_code, "actions =", r.json().get("count"),
          "bands =", r.json().get("by_band"))
    ok &= r.status_code == 200 and r.json().get("count", 0) > 0

    r = httpx.get(f"{base}/agents/portal", params={"lang": "en"})
    print("REST /agents/portal ->", r.status_code, "html chars =", len(r.text))
    ok &= r.status_code == 200 and "Agentic OS" in r.text

    pid = __import__("server").properties_db[0].id
    lead_id = __import__("server").leads_db[0].id

    r = httpx.post(f"{base}/transactions", json={"transaction_type": "sale", "price": 30_000_000,
                                                 "property_title": "Smoke txn"})
    tx_id = (r.json().get("transaction") or {}).get("id") if r.status_code == 201 else None
    print("REST /transactions (create) ->", r.status_code, "id =", bool(tx_id))
    ok &= r.status_code == 201 and bool(tx_id)

    r = httpx.post(f"{base}/transactions/{tx_id}/close", json={})
    print("REST /transactions/{id}/close ->", r.status_code, "gross =",
          r.json().get("commission", {}).get("gross"), "balanced =", r.json().get("balanced"))
    ok &= r.status_code == 200 and r.json().get("balanced") is True

    r = httpx.post(f"{base}/transactions/{tx_id}/report")
    print("REST /transactions/{id}/report ->", r.status_code, "html chars =", len(r.text))
    ok &= r.status_code == 200 and "Transaction summary" in r.text

    r = httpx.get(f"{base}/intelligence/buyer/anomalies")
    print("REST /intelligence/buyer/anomalies ->", r.status_code, "scanned =", r.json().get("scanned"),
          "bargains =", r.json().get("bargain_count"))
    ok &= r.status_code == 200 and r.json().get("scanned", 0) > 0

    r = httpx.get(f"{base}/intelligence/seller/cma/{pid}")
    print("REST /intelligence/seller/cma ->", r.status_code, "target =",
          r.json().get("price_range", {}).get("target"))
    ok &= r.status_code == 200 and r.json().get("price_range", {}).get("target", 0) > 0

    r = httpx.get(f"{base}/intelligence/investment/screen", params={"min_cap_rate": 0.02})
    print("REST /intelligence/investment/screen ->", r.status_code, "considered =", r.json().get("considered"),
          "passed =", r.json().get("passed"))
    ok &= r.status_code == 200 and r.json().get("passed", 0) >= 1

    r = httpx.get(f"{base}/leasing/funnel")
    print("REST /leasing/funnel ->", r.status_code, "inquiries =", r.json().get("inquiries"),
          "auto-handled =", r.json().get("auto_handled"))
    ok &= r.status_code == 200 and r.json().get("inquiries", 0) > 0

    r = httpx.get(f"{base}/leasing/portal")
    print("REST /leasing/portal ->", r.status_code, "html chars =", len(r.text))
    ok &= r.status_code == 200 and "Autonomous Leasing wing" in r.text

    r = httpx.get(f"{base}/marketing/funnel")
    print("REST /marketing/funnel ->", r.status_code, "leads =", r.json().get("leads"),
          "conversion =", r.json().get("conversion_pct"))
    ok &= r.status_code == 200 and r.json().get("leads", 0) > 0

    r = httpx.get(f"{base}/marketing/portal")
    print("REST /marketing/portal ->", r.status_code, "html chars =", len(r.text))
    ok &= r.status_code == 200 and "AI Marketing Conductor wing" in r.text

    r = httpx.get(f"{base}/commercial/products")
    print("REST /commercial/products ->", r.status_code, "products =", r.json().get("count"))
    ok &= r.status_code == 200 and r.json().get("count") == 8

    r = httpx.get(f"{base}/commercial/portal")
    print("REST /commercial/portal ->", r.status_code, "html chars =", len(r.text))
    ok &= r.status_code == 200 and "Commercialization wing" in r.text

    # --- product surfaces: MCP-for-brokers & Property Intelligence ---
    r = httpx.get(f"{base}/broker/contacts", params={"lifecycle": "hot", "min_intent_score": 30})
    print("REST /broker/contacts ->", r.status_code, "contacts =", r.json().get("returned"))
    ok &= r.status_code == 200 and r.json().get("count", 0) >= 1

    r = httpx.get(f"{base}/broker/commission-projection")
    print("REST /broker/commission-projection ->", r.status_code, "weighted =",
          r.json().get("weighted_pipeline_commission"))
    ok &= r.status_code == 200 and "weighted_pipeline_commission" in r.json()

    r = httpx.get(f"{base}/broker/property-gis", params={"property_id": pid})
    print("REST /broker/property-gis ->", r.status_code, "grade =", r.json().get("grade"),
          "score =", r.json().get("composite_score"))
    ok &= r.status_code == 200 and r.json().get("grade") in ("A", "B", "C", "D")

    r = httpx.get(f"{base}/broker/listing-draft/{pid}")
    print("REST /broker/listing-draft ->", r.status_code, "headline =",
          str(r.json().get("headline"))[:40])
    ok &= r.status_code == 200 and r.json().get("status") == "draft"

    r = httpx.get(f"{base}/property-intelligence/gis-score", params={"address": "Lahore"})
    print("REST /property-intelligence/gis-score ->", r.status_code,
          "grade =", r.json().get("grade"))
    ok &= r.status_code == 200 and "composite_score" in r.json()

    r = httpx.get(f"{base}/property-intelligence/accounting-snapshot/{pid}")
    print("REST /property-intelligence/accounting-snapshot ->", r.status_code, "cap =",
          r.json().get("cap_rate"))
    ok &= r.status_code == 200 and r.json().get("cap_rate", 0) > 0

    r = httpx.get(f"{base}/property-intelligence/market-intelligence")
    print("REST /property-intelligence/market-intelligence ->", r.status_code, "direction =",
          r.json().get("direction"))
    ok &= r.status_code == 200 and r.json().get("direction") in ("expanding", "stable", "softening")

    r = httpx.get(f"{base}/property-intelligence/seller-intent/{lead_id}")
    print("REST /property-intelligence/seller-intent ->", r.status_code, "band =",
          r.json().get("band"))
    ok &= r.status_code == 200 and "band" in r.json()

    # --- tools & utilities wing ---
    r = httpx.get(f"{base}/tools/overview")
    print("REST /tools/overview ->", r.status_code, "tools =", r.json().get("counts", {}).get("tools"),
          "categories =", r.json().get("counts", {}).get("categories"))
    ok &= r.status_code == 200 and r.json().get("counts", {}).get("tools", 0) >= 20

    r = httpx.post(f"{base}/tools/calculators/mortgage", json={"price": 10_000_000,
                                                               "down_payment": 2_000_000,
                                                               "annual_rate": 0.12, "years": 15})
    print("REST /tools/calculators/mortgage ->", r.status_code, "monthly =",
          r.json().get("monthly_payment"))
    ok &= r.status_code == 200 and r.json().get("monthly_payment", 0) > 0

    r = httpx.get(f"{base}/tools/convert/area", params={"value": 10, "from_unit": "marla",
                                                        "to_unit": "sqft"})
    print("REST /tools/convert/area ->", r.status_code, "sqft =", r.json().get("result", {}).get("value"))
    ok &= r.status_code == 200 and r.json().get("result", {}).get("value", 0) > 0

    r = httpx.get(f"{base}/tools/gis/crs")
    print("REST /tools/gis/crs ->", r.status_code, "systems =", r.json().get("count"))
    ok &= r.status_code == 200 and r.json().get("count", 0) >= 5

    r = httpx.get(f"{base}/tools/portal", params={"lang": "en"})
    print("REST /tools/portal ->", r.status_code, "html chars =", len(r.text))
    ok &= r.status_code == 200 and "Tools" in r.text and "tc-grid" in r.text

    # --- PMO wing (project management, monitoring & tracking) ---
    r = httpx.get(f"{base}/pmo/overview")
    print("REST /pmo/overview ->", r.status_code, "projects =",
          r.json().get("counts", {}).get("projects"), "tasks =", r.json().get("counts", {}).get("tasks"))
    ok &= r.status_code == 200 and r.json().get("counts", {}).get("projects", 0) >= 1

    r = httpx.get(f"{base}/pmo/projects")
    seeded_pm = r.json().get("projects", [{}])[0].get("id") if r.status_code == 200 else None
    print("REST /pmo/projects ->", r.status_code, "count =", r.json().get("count"),
          "health =", r.json().get("projects", [{}])[0].get("health"))
    ok &= r.status_code == 200 and r.json().get("count", 0) >= 1

    r = httpx.post(f"{base}/pmo/projects", json={"name": "Smoke Site", "project_type": "construction",
                                                "budget": 60_000_000, "start_date": "2026-05-04",
                                                "status": "active"})
    new_pm = (r.json().get("project") or {}).get("id") if r.status_code == 200 else None
    print("REST /pmo/projects (create) ->", r.status_code, "id =", bool(new_pm),
          "tasks =", r.json().get("tasks"))
    ok &= r.status_code == 200 and bool(new_pm) and r.json().get("tasks") == 16

    r = httpx.get(f"{base}/pmo/projects/{new_pm}/schedule")
    print("REST /pmo/projects/{id}/schedule ->", r.status_code, "duration =",
          r.json().get("duration_days"), "critical =", len(r.json().get("critical_path", [])))
    ok &= r.status_code == 200 and r.json().get("duration_days", 0) > 0
    ok &= len(r.json().get("critical_path", [])) > 0

    r = httpx.get(f"{base}/pmo/projects/{new_pm}/earned-value")
    print("REST /pmo/projects/{id}/earned-value ->", r.status_code, "EV =", r.json().get("EV"),
          "SPI =", r.json().get("SPI"))
    ok &= r.status_code == 200 and "EV" in r.json()

    r = httpx.get(f"{base}/pmo/projects/{new_pm}/health")
    print("REST /pmo/projects/{id}/health ->", r.status_code, "overall =", r.json().get("overall"),
          "bands =", r.json().get("bands"))
    ok &= r.status_code == 200 and r.json().get("overall") in ("green", "amber", "red")

    r = httpx.get(f"{base}/pmo/portfolio")
    print("REST /pmo/portfolio ->", r.status_code, "projects =", r.json().get("projects"),
          "SPI =", r.json().get("portfolio_spi"))
    ok &= r.status_code == 200 and r.json().get("projects", 0) >= 2

    r = httpx.get(f"{base}/pmo/alerts")
    print("REST /pmo/alerts ->", r.status_code, "alerts =", r.json().get("count"),
          "red =", r.json().get("red"))
    ok &= r.status_code == 200 and "alerts" in r.json()

    r = httpx.get(f"{base}/pmo/portal", params={"lang": "en"})
    print("REST /pmo/portal ->", r.status_code, "html chars =", len(r.text))
    ok &= r.status_code == 200 and "PMO" in r.text and "Project register" in r.text

    r = httpx.get(f"{base}/pmo/report.html", params={"project_id": seeded_pm, "lang": "en"})
    print("REST /pmo/report.html ->", r.status_code, "html chars =", len(r.text))
    ok &= r.status_code == 200 and "<html" in r.text.lower()

    r = httpx.delete(f"{base}/pmo/projects/{new_pm}")
    print("REST /pmo/projects/{id} (delete) ->", r.status_code, "deleted =", r.json().get("deleted"))
    ok &= r.status_code == 200 and r.json().get("deleted") is True

    # --- MCP should expose the same facilities (checked after initialize, below) ---
    r = httpx.post(f"{base}/v1/chat/completions", json={
        "model": "portal-realestate-rag",
        "messages": [{"role": "user", "content": "3 bedroom house in Islamabad"}],
    })
    msg = r.json().get("choices", [{}])[0].get("message", {}).get("content", "") if r.status_code == 200 else ""
    print("OPENAI /v1/chat/completions ->", r.status_code, "reply chars =", len(msg))
    ok &= r.status_code == 200 and len(msg) > 0

    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "smoke", "version": "1.0"},
        },
    }
    r = httpx.post(f"{base}/mcp", json=body, headers=headers)
    session_id = r.headers.get("mcp-session-id")
    print("MCP  /mcp initialize ->", r.status_code, "session =", session_id, "(optional in stateless)")
    ok &= r.status_code == 200 and '"result"' in r.text

    tl_headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    if session_id:
        tl_headers["mcp-session-id"] = session_id
    r = httpx.post(f"{base}/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, headers=tl_headers)
    mcp_new_tools = ["accounting_dashboard", "finance_mortgage_calculator", "poi_nearby",
                     "aoi_analyze", "portal_health", "global_search", "content_portal_home",
                     "ad_active", "gis_route", "poi_route", "auth_list_roles",
                     "agents_overview", "agent_run", "transaction_create", "buyer_recommend",
                     "seller_cma", "investment_screen", "leasing_inquiry", "marketing_qualify",
                     "commercial_products", "agentic_portal", "commercial_portal",
                     "search_contacts", "get_commission_projection", "analyze_property_gis",
                     "create_listing_draft", "get_gis_score", "get_accounting_snapshot",
                     "get_market_intelligence", "score_seller_intent",
                     "tools_overview", "tool_mortgage_calculator", "tools_portal",
                     "pmo_overview", "pm_create_project", "pm_schedule", "pm_earned_value",
                     "pm_health", "pm_portfolio", "pm_risk_matrix", "pm_portal"]
    print("MCP  /mcp tools/list ->", r.status_code, "new tools =",
          {t: (t in r.text) for t in mcp_new_tools})
    ok &= r.status_code == 200 and "portal_languages" in r.text and "portal_themes" in r.text
    ok &= all(t in r.text for t in mcp_new_tools)

    server.should_exit = True
    thread.join(timeout=10)
    print("\nSMOKE:", "PASS" if ok else "FAIL")


if __name__ == "__main__":
    main()
