"""
Integration test app — exercises the MCP server AND the FastAPI app together.

It proves that both protocols run off the *same* data store:

  1. MCP side   : connects to the in-process MCP server with `mcp.Client`,
                  lists tools/resources/prompts, calls tools and reads resources.
  2. FastAPI side: drives the REST app with FastAPI's TestClient.
  3. Cross-check: data created over MCP is visible over REST, and vice-versa.

Run:
    uv run python test_integration.py
"""

import asyncio
import base64
import json
import logging
import os
from typing import Any, Dict, List, Tuple

from mcp import Client
from fastapi.testclient import TestClient

import server as core
from api import app

# Keep the console output focused on the report.
for _name in ("httpx", "httpcore", "mcp", "uvicorn", "anyio", "asyncio"):
    logging.getLogger(_name).setLevel(logging.WARNING)
logging.getLogger().setLevel(logging.WARNING)

RESULTS: List[Tuple[str, bool, str]] = []
STATE: dict = {}


def check(name: str, condition: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(condition), detail))


def text_of(call_result: Any) -> str:
    parts = []
    for block in getattr(call_result, "content", []) or []:
        text = getattr(block, "text", None)
        if text is not None:
            parts.append(text)
    return "\n".join(parts)


class _SharedClient:
    """Context manager that hands back an already-entered ``TestClient``.

    ``TestClient(app)`` runs the app lifespan (which starts the MCP session
    manager — only startable once per process). This lets a later check-suite
    reuse the client that ``run_fastapi_checks`` already entered.
    """

    def __init__(self, client: TestClient) -> None:
        self._client = client

    def __enter__(self) -> TestClient:
        return self._client

    def __exit__(self, *exc: object) -> bool:
        return False


# ============================================================
# 1) MCP protocol
# ============================================================


async def run_mcp_checks() -> str | None:
    print("\n=== MCP protocol ===")
    async with Client(core.mcp) as client:
        tools = await client.list_tools()
        resources = await client.list_resources()
        templates = await client.list_resource_templates()
        prompts = await client.list_prompts()

        print(f"  tools={len(tools.tools)} resources={len(resources.resources)} "
              f"templates={len(templates.resource_templates)} prompts={len(prompts.prompts)}")

        check("MCP tools registered (>50)", len(tools.tools) > 50, str(len(tools.tools)))
        check("MCP resources registered (>10)", len(resources.resources) > 10, str(len(resources.resources)))
        check("MCP resource templates registered (>5)", len(templates.resource_templates) > 5,
              str(len(templates.resource_templates)))
        check("MCP prompts registered (>=3)", len(prompts.prompts) >= 3, str(len(prompts.prompts)))

        # --- call some tools ---
        r = json.loads(text_of(await client.call_tool("health_check", {})))
        check("tool: health_check", r.get("status") == "ok", str(r))

        r = json.loads(text_of(await client.call_tool("search_properties", {"city": "Lahore", "limit": 5})))
        check("tool: search_properties (Lahore)", r.get("count", 0) > 0, f"count={r.get('count')}")

        r = json.loads(text_of(await client.call_tool("search_nearby_properties",
                                                      {"latitude": 31.5204, "longitude": 74.3587, "radius_km": 10})))
        check("tool: search_nearby_properties", r.get("count", 0) > 0, f"count={r.get('count')}")

        r = json.loads(text_of(await client.call_tool("convert_area",
                                                      {"value": 1, "from_unit": "kanal", "to_unit": "marla"})))
        check("tool: convert_area (1 kanal = 20 marla)", r.get("result") == 20, str(r))

        r = json.loads(text_of(await client.call_tool("rag_search", {"query": "5 bedroom house in Lahore", "top_k": 3})))
        check("tool: rag_search", r.get("count", 0) > 0, f"count={r.get('count')}")

        r = json.loads(text_of(await client.call_tool("crm_dashboard", {})))
        check("tool: crm_dashboard", r.get("leads", {}).get("total", 0) > 0, str(r.get("leads")))

        r = json.loads(text_of(await client.call_tool("crm_pipeline_summary", {})))
        check("tool: crm_pipeline_summary", r.get("total_deals", 0) > 0, f"deals={r.get('total_deals')}")

        # --- GIS tools ---
        r = json.loads(text_of(await client.call_tool("gis_list_base_maps", {})))
        check("tool: gis_list_base_maps", r.get("count", 0) >= 5, f"count={r.get('count')}")

        r = json.loads(text_of(await client.call_tool("gis_list_layers", {})))
        check("tool: gis_list_layers", r.get("count", 0) > 0, f"count={r.get('count')}")

        r = json.loads(text_of(await client.call_tool("gis_list_master_plans", {})))
        check("tool: gis_list_master_plans", r.get("count", 0) > 0, f"count={r.get('count')}")

        r = json.loads(text_of(await client.call_tool("gis_properties_in_bounds", {
            "south": 31.40, "west": 74.20, "north": 31.55, "east": 74.40,
        })))
        check("tool: gis_properties_in_bounds", r.get("count", 0) > 0, f"count={r.get('count')}")

        r = json.loads(text_of(await client.call_tool("gis_polygon_area", {
            "coordinates": [[31.4460, 74.2740], [31.4460, 74.2870], [31.4560, 74.2870], [31.4560, 74.2740]],
        })))
        check("tool: gis_polygon_area", r.get("area_sqm", 0) > 0, str(r.get("area_sqm")))

        # --- create a master-plan layer over MCP; verify it over REST later ---
        r = json.loads(text_of(await client.call_tool("gis_add_master_plan", {
            "entity_type": "city",
            "entity_id": core.cities_db[0].id,
            "name": "MCP Test Master Plan",
            "north": 31.60, "south": 31.50, "east": 74.40, "west": 74.30,
        })))
        mcp_layer_id = r.get("layer", {}).get("id")
        check("tool: gis_add_master_plan (over MCP)", bool(mcp_layer_id), str(r)[:120])

        content = await client.read_resource("gis://basemaps")
        uri_text = "".join(getattr(c, "text", "") for c in content.contents)
        check("resource: gis://basemaps", "google_" in uri_text, uri_text[:80].replace("\n", " "))

        # --- GIS analysis: buffers, cost, population, economics, maps, reports ---
        scheme_id = core.housing_schemes_db[0].id

        r = json.loads(text_of(await client.call_tool("gis_analysis_assumptions", {})))
        check("tool: gis_analysis_assumptions", r.get("avg_household_size", 0) > 0, str(r.get("avg_household_size")))

        r = json.loads(text_of(await client.call_tool("gis_buffer_point",
                                                      {"latitude": 31.4504, "longitude": 74.28, "radius_m": 800})))
        check("tool: gis_buffer_point", r.get("area_sqm", 0) > 0, str(r.get("area_sqm")))

        r = json.loads(text_of(await client.call_tool("gis_ring_analysis",
                                                      {"latitude": 31.4504, "longitude": 74.28, "radii_km": [1, 3, 5]})))
        check("tool: gis_ring_analysis", len(r.get("rings", [])) == 3, f"rings={len(r.get('rings', []))}")

        r = json.loads(text_of(await client.call_tool("gis_area_analysis", {"entity_type": "scheme", "entity_id": scheme_id})))
        check("tool: gis_area_analysis", r.get("development_cost", {}).get("total", 0) > 0
              and r.get("economic_impact", {}).get("jobs_total", 0) > 0,
              f"cost={r.get('development_cost', {}).get('total')}")

        r = json.loads(text_of(await client.call_tool("gis_feature_table",
                                                      {"scope_type": "scheme", "scope_id": scheme_id, "metric": "population"})))
        check("tool: gis_feature_table", r.get("count", 0) > 0, f"count={r.get('count')}")

        html = text_of(await client.call_tool("gis_thematic_map",
                                              {"scope_type": "scheme", "scope_id": scheme_id, "metric": "market_value"}))
        check("tool: gis_thematic_map", "choropleth" in html and "legend" in html, f"chars={len(html)}")

        html = text_of(await client.call_tool("gis_area_report", {"entity_type": "scheme", "entity_id": scheme_id}))
        check("tool: gis_area_report", "Economic impact" in html and "srcdoc" in html, f"chars={len(html)}")

        # --- cost / development, forecasting, news ---
        r = json.loads(text_of(await client.call_tool("gis_cost_development_analysis",
                                                      {"entity_type": "scheme", "entity_id": scheme_id})))
        cd = r.get("cost_development", {})
        check("tool: gis_cost_development_analysis", cd.get("gross_development_value", 0) > 0
              and cd.get("cost_breakdown", {}).get("land_cost", 0) > 0, str(cd.get("viability")))

        r = json.loads(text_of(await client.call_tool("gis_market_factors", {"entity_type": "scheme", "entity_id": scheme_id})))
        check("tool: gis_market_factors", r.get("index", {}).get("composite", 0) > 0
              and len(r.get("factors", {})) >= 5, str(r.get("index")))

        r = json.loads(text_of(await client.call_tool("gis_forecast", {"entity_type": "scheme", "entity_id": scheme_id, "years": 5})))
        fc = r.get("forecast", {})
        check("tool: gis_forecast", fc.get("composite_index", 0) > 0 and len(fc.get("scenarios", {})) == 4
              and len(fc.get("expected", [])) == 6, f"cagr={fc.get('base_cagr')}")

        r = json.loads(text_of(await client.call_tool("gis_scenario_analysis",
                                                      {"entity_type": "scheme", "entity_id": scheme_id, "years": 5})))
        check("tool: gis_scenario_analysis", len(r.get("scenarios", {})) == 4, str(len(r.get("scenarios", {}))))

        r = json.loads(text_of(await client.call_tool("news_channels", {})))
        check("tool: news_channels", r.get("count", 0) > 3, f"channels={r.get('count')}")

        r = json.loads(text_of(await client.call_tool("news_list", {"city": "Lahore"})))
        check("tool: news_list (Lahore)", r.get("count", 0) > 0, f"count={r.get('count')}")

        r = json.loads(text_of(await client.call_tool("news_impact", {"city": "Lahore"})))
        check("tool: news_impact", r.get("summary", {}).get("count", 0) > 0, str(r.get("summary", {}).get("net_sentiment")))

        r = json.loads(text_of(await client.call_tool("news_add", {
            "title": "MCP test headline", "source": "Test Wire", "category": "market",
            "sentiment": "positive", "city_id": core.cities_db[0].id,
        })))
        check("tool: news_add (over MCP)", bool(r.get("id")), str(r.get("impact_score")))

        html = text_of(await client.call_tool("news_ticker", {"city": "Lahore", "limit": 10}))
        check("tool: news_ticker", "portal-ticker" in html and "tk-item" in html, f"chars={len(html)}")

        html = text_of(await client.call_tool("gis_outlook_report", {"entity_type": "scheme", "entity_id": scheme_id}))
        check("tool: gis_outlook_report", "portal-ticker" in html and "Future predictions" in html
              and "Investment Outlook" in html, f"chars={len(html)}")

        content = await client.read_resource("news://ticker")
        uri_text = "".join(getattr(c, "text", "") for c in content.contents)
        check("resource: news://ticker", "portal-ticker" in uri_text, uri_text[:60].replace("\n", " "))

        content = await client.read_resource(f"gis://forecast/scheme/{scheme_id}")
        uri_text = "".join(getattr(c, "text", "") for c in content.contents)
        check("resource: gis://forecast", "scenarios" in uri_text, uri_text[:60].replace("\n", " "))

        content = await client.read_resource("gis://analysis/assumptions")
        uri_text = "".join(getattr(c, "text", "") for c in content.contents)
        check("resource: gis://analysis/assumptions", "economic_multiplier" in uri_text, uri_text[:60].replace("\n", " "))

        # --- authentication over MCP: OTP signup -> verify -> token ---
        r = json.loads(text_of(await client.call_tool("auth_config", {})))
        check("tool: auth_config", r.get("otp_length") == 6 and r.get("users", 0) >= 3, str(r.get("users")))

        r = json.loads(text_of(await client.call_tool("auth_signup", {
            "email": "mcp@portal.test", "mobile": "0346 666 0101",
            "password": "Secret@123", "name": "MCP Auth User",
        })))
        check("tool: auth_signup", r.get("otp_required") is True and r.get("status") == "pending"
              and r.get("user", {}).get("customer_id"), str(r.get("error") or r.get("status")))

        r = json.loads(text_of(await client.call_tool("auth_get_otp", {"identifier": "mcp@portal.test"})))
        mcp_code = r.get("code")
        check("tool: auth_get_otp", bool(mcp_code), str(r.get("code")))

        r = json.loads(text_of(await client.call_tool("auth_verify_otp",
                                                      {"identifier": "mcp@portal.test", "code": mcp_code})))
        mcp_auth_token = r.get("token")
        check("tool: auth_verify_otp", r.get("verified") is True and bool(mcp_auth_token), str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("auth_me", {"token": mcp_auth_token})))
        check("tool: auth_me", r.get("authenticated") is True
              and r.get("user", {}).get("email") == "mcp@portal.test", str(r.get("error")))

        content = await client.read_resource("auth://users")
        uri_text = "".join(getattr(c, "text", "") for c in content.contents)
        check("resource: auth://users", "mcp@portal.test" in uri_text, uri_text[:60].replace("\n", " "))

        # --- dual-language + themes over MCP ---
        r = json.loads(text_of(await client.call_tool("portal_languages", {})))
        check("tool: portal_languages", [l["code"] for l in r.get("languages", [])] == ["en", "ur"],
              str(r.get("count")))

        r = json.loads(text_of(await client.call_tool("portal_themes", {})))
        check("tool: portal_themes", [t["code"] for t in r.get("themes", [])] == ["auto", "light", "dark"]
              and "--ink" in r.get("tokens", {}).get("dark", {}), str(r.get("count")))

        r = json.loads(text_of(await client.call_tool("portal_strings", {"lang": "ur"})))
        check("tool: portal_strings", r.get("language") == "ur" and r.get("count", 0) > 50, str(r.get("count")))

        html = text_of(await client.call_tool("gis_map_preview", {
            "entity_type": "scheme", "entity_id": scheme_id, "lang": "ur", "theme": "dark",
        }))
        check("tool: gis_map_preview (ur/dark)", 'dir="rtl"' in html and 'html[data-theme="dark"]' in html,
              html[:60])

        html = text_of(await client.call_tool("gis_area_report", {
            "entity_type": "scheme", "entity_id": scheme_id, "lang": "ur", "theme": "dark",
        }))
        check("tool: gis_area_report (ur/dark)", 'dir="rtl"' in html and "آبادی" in html, html[:60])

        html = text_of(await client.call_tool("news_ticker", {"city": "Lahore", "lang": "ur"}))
        check("tool: news_ticker (ur)", 'dir="rtl"' in html and "رئیل اسٹیٹ خبریں" in html, html[:60])

        content = await client.read_resource("gis://languages")
        uri_text = "".join(getattr(c, "text", "") for c in content.contents)
        check("resource: gis://languages", "ur" in uri_text and "rtl" in uri_text, uri_text[:60].replace("\n", " "))

        content = await client.read_resource("gis://strings/ur")
        uri_text = "".join(getattr(c, "text", "") for c in content.contents)
        check("resource: gis://strings/ur", "مربع فٹ" in uri_text, uri_text[:60].replace("\n", " "))

        content = await client.read_resource("gis://themes")
        uri_text = "".join(getattr(c, "text", "") for c in content.contents)
        check("resource: gis://themes", "--surface" in uri_text, uri_text[:60].replace("\n", " "))

        # --- accounting + finance (ROI) over MCP ---
        r = json.loads(text_of(await client.call_tool("accounting_info", {})))
        check("tool: accounting_info", r.get("counts", {}).get("accounts", 0) > 30, str(r.get("counts")))

        r = json.loads(text_of(await client.call_tool("accounting_trial_balance", {})))
        check("tool: accounting_trial_balance", r.get("balanced") is True and r.get("total_debit", 0) > 0,
              f"debit={r.get('total_debit')}")

        r = json.loads(text_of(await client.call_tool("accounting_balance_sheet", {})))
        check("tool: accounting_balance_sheet", r.get("balanced") is True and r.get("total_assets", 0) > 0,
              f"assets={r.get('total_assets')}")

        r = json.loads(text_of(await client.call_tool("accounting_profit_and_loss", {})))
        check("tool: accounting_profit_and_loss", r.get("total_income", 0) > 0 and r.get("net_profit", 0) != 0,
              f"net={r.get('net_profit')}")

        r = json.loads(text_of(await client.call_tool("accounting_dashboard", {})))
        check("tool: accounting_dashboard", r.get("total_assets", 0) > 0 and r.get("revenue", 0) > 0,
              f"assets={r.get('total_assets')}")

        r = json.loads(text_of(await client.call_tool("accounting_rent_roll", {})))
        check("tool: accounting_rent_roll", r.get("monthly_rent", 0) > 0 and r.get("leases", 0) > 0,
              f"monthly={r.get('monthly_rent')}")

        r = json.loads(text_of(await client.call_tool("accounting_invoice_aging", {})))
        check("tool: accounting_invoice_aging", len(r.get("buckets", {})) == 5 and r.get("total", 0) > 0,
              str(r.get("total")))

        r = json.loads(text_of(await client.call_tool("accounting_journal_post", {
            "lines": [{"account": "1010", "debit": 5000}, {"account": "4030", "credit": 5000}],
            "memo": "MCP integration journal",
        })))
        mcp_entry_lines = r.get("lines", [])
        mcp_debit = sum(l.get("debit", 0) for l in mcp_entry_lines)
        mcp_credit = sum(l.get("credit", 0) for l in mcp_entry_lines)
        check("tool: accounting_journal_post (balanced)", bool(r.get("id")) and abs(mcp_debit - mcp_credit) < 0.01,
              str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("accounting_cash_flow", {})))
        check("tool: accounting_cash_flow", "operating" in r and "closing_cash" in r, str(r.get("closing_cash")))

        r = json.loads(text_of(await client.call_tool("finance_mortgage_calculator", {"principal": 8_000_000})))
        check("tool: finance_mortgage_calculator", r.get("payment", 0) > 0 and len(r.get("schedule", [])) > 0,
              str(r.get("payment")))

        r = json.loads(text_of(await client.call_tool("finance_investment_metrics",
                                                      {"cashflows": [-10_000_000, 3_000_000, 4_000_000, 5_000_000, 4_000_000]})))
        check("tool: finance_investment_metrics", r.get("npv") is not None and r.get("irr") is not None,
              f"irr={r.get('irr')}")

        r = json.loads(text_of(await client.call_tool("finance_property_roi",
                                                      {"purchase_price": 20_000_000, "annual_rent": 1_800_000})))
        check("tool: finance_property_roi", r.get("gross_rental_yield", 0) > 0
              and r.get("base", {}).get("irr") is not None, str(r.get("gross_rental_yield")))

        leased_property = core.accounting.leases_db[0].property_id
        r = json.loads(text_of(await client.call_tool("finance_rental_yield", {"property_id": leased_property})))
        check("tool: finance_rental_yield", r.get("gross_yield", 0) > 0, str(r.get("gross_yield")))

        r = json.loads(text_of(await client.call_tool("finance_portfolio_roi", {})))
        check("tool: finance_portfolio_roi", r.get("market_value", 0) > 0 and r.get("roi", {}).get("base") is not None,
              f"value={r.get('market_value')}")

        content = await client.read_resource("accounting://trial-balance")
        uri_text = "".join(getattr(c, "text", "") for c in content.contents)
        check("resource: accounting://trial-balance", '"balanced"' in uri_text, uri_text[:60].replace("\n", " "))

        content = await client.read_resource("accounting://dashboard")
        uri_text = "".join(getattr(c, "text", "") for c in content.contents)
        check("resource: accounting://dashboard", "total_assets" in uri_text, uri_text[:60].replace("\n", " "))

        # --- POI over MCP ---
        r = json.loads(text_of(await client.call_tool("poi_categories", {})))
        check("tool: poi_categories", r.get("count", 0) > 0, f"count={r.get('count')}")

        r = json.loads(text_of(await client.call_tool("poi_nearby",
                                                      {"latitude": 31.4504, "longitude": 74.2810, "radius_km": 3})))
        check("tool: poi_nearby", r.get("count", 0) > 0, f"count={r.get('count')}")

        r = json.loads(text_of(await client.call_tool("poi_add", {
            "name": "MCP test clinic", "latitude": 31.4505, "longitude": 74.2815, "category": "health",
            "city_id": core.cities_db[0].id,
        })))
        STATE["poi_id"] = r.get("id")
        check("tool: poi_add (over MCP)", bool(STATE["poi_id"]), str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("poi_accessibility_score",
                                                      {"latitude": 31.4504, "longitude": 74.2810, "radius_km": 3})))
        check("tool: poi_accessibility_score", r.get("score", 0) > 0 and r.get("band"), str(r.get("score")))

        r = json.loads(text_of(await client.call_tool("poi_nearest",
                                                      {"latitude": 31.4504, "longitude": 74.2810})))
        check("tool: poi_nearest", r.get("count", 0) > 0, f"count={r.get('count')}")

        content = await client.read_resource("poi://categories")
        uri_text = "".join(getattr(c, "text", "") for c in content.contents)
        check("resource: poi://categories", "education" in uri_text, uri_text[:60].replace("\n", " "))

        # --- AOI over MCP ---
        r = json.loads(text_of(await client.call_tool("aoi_list", {})))
        check("tool: aoi_list", r.get("count", 0) > 0, f"count={r.get('count')}")
        mcp_aoi_id = r.get("areas", [{}])[0].get("id")

        r = json.loads(text_of(await client.call_tool("aoi_analyze", {"aoi_id": mcp_aoi_id})))
        check("tool: aoi_analyze", r.get("forecast", {}).get("composite_index", 0) > 0
              and r.get("poi_summary", {}).get("total", 0) > 0, str(r.get("forecast", {}).get("composite_index")))

        r = json.loads(text_of(await client.call_tool("aoi_watch", {"aoi_id": mcp_aoi_id})))
        check("tool: aoi_watch", r.get("count", 0) > 0 and "summary" in r, f"count={r.get('count')}")

        html = text_of(await client.call_tool("aoi_map", {"aoi_id": mcp_aoi_id}))
        check("tool: aoi_map", "leaflet" in html.lower(), f"chars={len(html)}")

        html = text_of(await client.call_tool("aoi_report", {"aoi_id": mcp_aoi_id, "lang": "ur", "theme": "dark"}))
        check("tool: aoi_report (ur/dark)", 'dir="rtl"' in html and "Points of interest" in html, f"chars={len(html)}")

        content = await client.read_resource("aoi://all")
        uri_text = "".join(getattr(c, "text", "") for c in content.contents)
        check("resource: aoi://all", "areas" in uri_text, uri_text[:60].replace("\n", " "))

        # --- portal discovery / analytics over MCP ---
        r = json.loads(text_of(await client.call_tool("portal_health", {})))
        check("tool: portal_health", r.get("status") == "ok" and r.get("mcp", {}).get("tools", 0) > 200,
              f"tools={r.get('mcp', {}).get('tools')}")

        r = json.loads(text_of(await client.call_tool("portal_catalog", {})))
        check("tool: portal_catalog", r.get("tool_count", 0) > 200 and "accounting" in r.get("groups", {}),
              f"groups={len(r.get('groups', {}))}")

        r = json.loads(text_of(await client.call_tool("portal_schema", {"model": "invoice"})))
        check("tool: portal_schema", "total" in r.get("schema", {}).get("properties", {}), str(r.get("model")))

        r = json.loads(text_of(await client.call_tool("global_search", {"query": "lahore"})))
        check("tool: global_search", r.get("total", 0) > 0, f"total={r.get('total')}")

        r = json.loads(text_of(await client.call_tool("portal_statistics", {})))
        check("tool: portal_statistics", r.get("inventory", {}).get("properties", 0) > 0
              and r.get("finance", {}).get("total_assets", 0) > 0, str(r.get("inventory", {}).get("properties")))

        r = json.loads(text_of(await client.call_tool("property_availability", {"city": "Lahore"})))
        check("tool: property_availability", r.get("count", 0) > 0 and "by_status" in r, f"count={r.get('count')}")

        r = json.loads(text_of(await client.call_tool("market_trends", {"city": "Lahore"})))
        check("tool: market_trends", r.get("forecast", {}).get("base_cagr", 0) > 0, str(r.get("forecast", {}).get("base_cagr")))

        html = text_of(await client.call_tool("gis_point_map", {"latitude": 31.4504, "longitude": 74.2810,
                                                                "include_poi": True}))
        check("tool: gis_point_map (poi)", "leaflet" in html.lower(), f"chars={len(html)}")

        prompt = await client.get_prompt("financial_review_prompt", {"period": "FY2026"})
        check("prompt: financial_review_prompt", len(prompt.messages) > 0, str(len(prompt.messages)))

        prompt = await client.get_prompt("site_selection_prompt", {"city": "Lahore"})
        check("prompt: site_selection_prompt", len(prompt.messages) > 0, str(len(prompt.messages)))

        # --- portal content + advertising over MCP ---
        r = json.loads(text_of(await client.call_tool("content_overview", {})))
        check("tool: content_overview", r.get("counts", {}).get("pages", 0) > 0
              and r.get("counts", {}).get("advertisements", 0) > 0, str(r.get("counts")))

        r = json.loads(text_of(await client.call_tool("content_page_list", {})))
        check("tool: content_page_list", r.get("count", 0) > 0, f"count={r.get('count')}")

        r = json.loads(text_of(await client.call_tool("content_page_get", {"key": "about"})))
        check("tool: content_page_get (about)", r.get("key") == "about", str(r.get("key")))

        r = json.loads(text_of(await client.call_tool("content_history", {})))
        check("tool: content_history", r.get("count", 0) > 0 and len(r.get("kinds", [])) > 0, f"count={r.get('count')}")

        r = json.loads(text_of(await client.call_tool("content_contact", {})))
        check("tool: content_contact", r.get("count", 0) > 0, f"count={r.get('count')}")

        r = json.loads(text_of(await client.call_tool("content_success_stories", {})))
        check("tool: content_success_stories", r.get("count", 0) > 0, f"count={r.get('count')}")

        r = json.loads(text_of(await client.call_tool("content_navigation", {})))
        check("tool: content_navigation", len(r.get("items", [])) > 0, f"items={len(r.get('items', []))}")

        r = json.loads(text_of(await client.call_tool("content_site", {"lang": "ur"})))
        check("tool: content_site (ur)", len(r.get("layout", [])) > 0, f"blocks={len(r.get('layout', []))}")

        html = text_of(await client.call_tool("content_portal_home", {"lang": "ur", "theme": "dark"}))
        check("tool: content_portal_home (ur/dark)", "ad-section" in html and 'dir="rtl"' in html,
              f"chars={len(html)}")

        r = json.loads(text_of(await client.call_tool("ad_categories", {})))
        check("tool: ad_categories", r.get("count", 0) >= 10, f"count={r.get('count')}")

        r = json.loads(text_of(await client.call_tool("ad_slots", {})))
        check("tool: ad_slots", r.get("count", 0) >= 5, f"count={r.get('count')}")

        r = json.loads(text_of(await client.call_tool("ad_active", {"slot": "hero"})))
        check("tool: ad_active (hero)", r.get("count", 0) > 0, f"count={r.get('count')}")

        r = json.loads(text_of(await client.call_tool("ad_section", {"slot": "infeed", "category": "materials"})))
        check("tool: ad_section (materials)", r.get("kind") == "ads" and r.get("count", 0) >= 0, str(r.get("kind")))

        r = json.loads(text_of(await client.call_tool("ad_performance", {})))
        check("tool: ad_performance", r.get("totals", {}).get("ads", 0) > 0, str(r.get("totals", {}).get("ads")))

        r = json.loads(text_of(await client.call_tool("ad_list", {"limit": 5})))
        check("tool: ad_list", r.get("count", 0) > 0, f"count={r.get('count')}")
        mcp_ad_id = r.get("advertisements", [{}])[0].get("id")

        if mcp_ad_id:
            r = json.loads(text_of(await client.call_tool("ad_track", {"ad_id": mcp_ad_id, "event": "click"})))
            check("tool: ad_track (click)", r.get("clicks", 0) >= 1, str(r))

        html = text_of(await client.call_tool("ad_report", {}))
        check("tool: ad_report", "ad-section" in html or "Sponsored" in html, f"chars={len(html)}")

        html = text_of(await client.call_tool("ad_preview", {"slot": "hero"}))
        check("tool: ad_preview", "ad-card" in html or "ad-section" in html, f"chars={len(html)}")

        # --- routing over MCP (on foot / by car) ---
        r = json.loads(text_of(await client.call_tool("gis_travel_modes", {})))
        check("tool: gis_travel_modes", "walk" in [m["mode"] for m in r.get("modes", [])], str(r.get("default")))

        r = json.loads(text_of(await client.call_tool("gis_road_classes", {})))
        check("tool: gis_road_classes", r.get("count", 0) > 0, f"count={r.get('count')}")

        route_args = {"origin_latitude": 31.4504, "origin_longitude": 74.2810,
                      "destination_latitude": 31.4690, "destination_longitude": 74.4120}
        r = json.loads(text_of(await client.call_tool("gis_route", {**route_args, "mode": "drive",
                                                                    "alternatives": 2})))
        check("tool: gis_route (drive)", r.get("best", {}).get("distance_m", 0) > 0
              and r.get("best", {}).get("duration_s", 0) > 0, str(r.get("best", {}).get("distance_km")))
        check("tool: gis_route alternatives", r.get("alternative_count", 0) >= 0, str(r.get("alternative_count")))

        r = json.loads(text_of(await client.call_tool("gis_route_compare", route_args)))
        check("tool: gis_route_compare", set(r.get("modes", {})) >= {"walk", "drive"}, str(list(r.get("modes", {}))))

        r = json.loads(text_of(await client.call_tool("gis_route_matrix",
                                                      {"poi_ids": ["Smart City Public School",
                                                                   "Downtown Shopping Mall",
                                                                   "City Care Hospital"], "mode": "drive"})))
        check("tool: gis_route_matrix", len(r.get("matrix", [])) == 3, f"points={len(r.get('points', []))}")

        r = json.loads(text_of(await client.call_tool("poi_route",
                                                      {"origin_poi": "Smart City Public School",
                                                       "destination_poi": "Downtown Shopping Mall",
                                                       "mode": "walk"})))
        check("tool: poi_route (walk)", r.get("origin_poi", {}).get("name") is not None, str(r.get("mode")))

        html = text_of(await client.call_tool("gis_route_map", {**route_args, "mode": "drive"}))
        check("tool: gis_route_map", "leaflet" in html.lower() and "LineString" in html, f"chars={len(html)}")

        r = json.loads(text_of(await client.call_tool("gis_add_road_network", {
            "name": "mcp-ways",
            "ways": [{"coordinates": [[31.45, 74.27], [31.46, 74.28], [31.47, 74.29]],
                      "road_class": "arterial", "name": "Demo Road"}],
        })))
        check("tool: gis_add_road_network", r.get("nodes", 0) == 3, str(r.get("nodes")))

        r = json.loads(text_of(await client.call_tool("gis_list_road_networks", {})))
        check("tool: gis_list_road_networks", r.get("count", 0) > 0, f"count={r.get('count')}")

        # --- portal users & roles over MCP ---
        r = json.loads(text_of(await client.call_tool("auth_list_roles", {})))
        check("tool: auth_list_roles", r.get("count", 0) >= 10, f"count={r.get('count')}")

        r = json.loads(text_of(await client.call_tool("auth_role_summary", {})))
        check("tool: auth_role_summary", r.get("permissions", 0) > 0 and r.get("roles", 0) > 0,
              f"roles={r.get('roles')}")

        r = json.loads(text_of(await client.call_tool("auth_permissions", {})))
        check("tool: auth_permissions", r.get("count", 0) > 0, f"count={r.get('count')}")

        r = json.loads(text_of(await client.call_tool("auth_get_role", {"name": "agent"})))
        check("tool: auth_get_role (agent)", r.get("name") == "agent", str(r.get("name")))

        r = json.loads(text_of(await client.call_tool("auth_users_by_role", {"role": "agent"})))
        check("tool: auth_users_by_role", r.get("count", 0) > 0, f"count={r.get('count')}")

        r = json.loads(text_of(await client.call_tool("auth_create_role", {
            "name": "mcp_temp_role", "label": "MCP Temp", "portal_area": "staff",
            "permissions": ["content.view"]})))
        check("tool: auth_create_role", r.get("name") == "mcp_temp_role", str(r.get("name")))
        if r.get("name") == "mcp_temp_role":
            r2 = json.loads(text_of(await client.call_tool("auth_delete_role", {"name": "mcp_temp_role"})))
            check("tool: auth_delete_role", r2.get("deleted") == "mcp_temp_role", str(r2))

        # --- content / ads / roles / routes resources & prompts ---
        for uri, needle in (("content://overview", "counts"), ("content://pages", "pages"),
                            ("ads://all", "advertisements"), ("ads://slots", "slots"),
                            ("roles://all", "roles"), ("roles://permissions", "permissions"),
                            ("routes://config", "modes")):
            body = await client.read_resource(uri)
            uri_text = "".join(getattr(c, "text", "") for c in body.contents)
            check(f"resource: {uri}", needle in uri_text, uri_text[:70].replace("\n", " "))

        for uri, needle in (("content://page/about", "about"),
                            ("roles://role/agent", "agent"),
                            ("content://portal-home", "ad-section")):
            body = await client.read_resource(uri)
            uri_text = "".join(getattr(c, "text", "") for c in body.contents)
            check(f"resource template: {uri}", needle in uri_text, uri_text[:70].replace("\n", " "))

        for pname, pargs in (("content_review_prompt", {"lang": "en"}),
                             ("ad_campaign_prompt", {"advertiser": "SmartNest"}),
                             ("route_planning_prompt", {"origin": "A", "destination": "B"}),
                             ("role_assignment_prompt", {"persona": "agent"})):
            prompt = await client.get_prompt(pname, pargs)
            check(f"prompt: {pname}", len(prompt.messages) > 0, str(len(prompt.messages)))

        # --- create a lead over MCP; we'll verify it over REST later ---
        r = json.loads(text_of(await client.call_tool("crm_add_lead", {
            "name": "MCP Created Lead",
            "city_id": core.cities_db[0].id,
            "interest_use_type": "residential",
            "budget_max": 50_000_000,
        })))
        mcp_lead_id = r.get("id")
        check("tool: crm_add_lead (over MCP)", bool(mcp_lead_id), str(mcp_lead_id))

        # --- read a resource ---
        content = await client.read_resource("cities://all")
        uri_text = "".join(getattr(c, "text", "") for c in content.contents)
        check("resource: cities://all", '"count"' in uri_text, uri_text[:80].replace("\n", " "))

        content = await client.read_resource("crm://pipeline")
        uri_text = "".join(getattr(c, "text", "") for c in content.contents)
        check("resource: crm://pipeline", "stages" in uri_text, uri_text[:80].replace("\n", " "))

        # --- get a prompt ---
        prompt = await client.get_prompt("property_recommendation", {"budget": "50m", "city": "Lahore"})
        check("prompt: property_recommendation", len(prompt.messages) > 0, str(len(prompt.messages)))

    return mcp_lead_id, mcp_layer_id  # type: ignore[return-value]


# ============================================================
# 1b) Construction & maintenance wings (MCP)
# ============================================================


async def run_wing_checks() -> None:
    print("\n=== Construction & maintenance wings (MCP) ===")
    async with Client(core.mcp) as client:
        # ---------------- construction ----------------
        r = json.loads(text_of(await client.call_tool("construction_overview", {})))
        check("tool: construction_overview", r["counts"]["systems"] >= 10, str(r["counts"]))

        r = json.loads(text_of(await client.call_tool("construction_techniques", {})))
        check("tool: construction_techniques", r["count"] >= 10, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("construction_technique", {"key": "rcc_frame"})))
        check("tool: construction_technique", r.get("key") == "rcc_frame" and r.get("cost_factor"),
              str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("construction_materials", {"category": "steel"})))
        check("tool: construction_materials", r["count"] >= 2, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("construction_material", {"key": "cement_opc"})))
        check("tool: construction_material", r.get("key") == "cement_opc", str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("construction_element_rates", {})))
        check("tool: construction_element_rates", r["count"] >= 10, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("construction_rate_analysis",
                                                      {"element": "rcc", "city": "Karachi"})))
        check("tool: construction_rate_analysis", r["total_rate"] > 0 and r["shares"]["material"] > 0,
              str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("construction_estimate", {
            "covered_area": 2722.5, "floors": 2, "building_type": "house",
            "quality_tier": "standard", "system": "rcc_frame"})))
        check("tool: construction_estimate", r["cost"]["total"] > 0 and r["cost"]["cost_per_sqft"] > 1000,
              str(r.get("error")))
        check("tool: construction_estimate element shares sum to 100",
              abs(sum(e["share_pct"] for e in r["elements"]) - 100.0) < 0.5,
              str(sum(e["share_pct"] for e in r["elements"])))
        STATE["est_id"] = None

        r = json.loads(text_of(await client.call_tool("construction_timeline", {"covered_area": 2000})))
        check("tool: construction_timeline", r["total_days"] > 0 and len(r["phases"]) >= 8,
              str(len(r.get("phases", []))))

        r = json.loads(text_of(await client.call_tool("construction_takeoff", {"covered_area": 2000})))
        check("tool: construction_takeoff", len(r["lines"]) >= 8 and r["material_value"] > 0,
              str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("construction_compare", {"covered_area": 2000})))
        check("tool: construction_compare", r["count"] >= 3 and r["cheapest"] is not None,
              str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("construction_impact", {
            "covered_area": 2000, "from_tier": "standard", "to_tier": "premium"})))
        check("tool: construction_impact", r["extra_cost"] > 0 and r["value_uplift"] > 0,
              str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("construction_advisory", {
            "plot_area": 2722.5, "floors": 2, "soil": "clay", "seismic_zone": "2A"})))
        check("tool: construction_advisory", bool(r.get("recommended_system")) and bool(r.get("foundation_recommendation")),
              str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("construction_guidelines", {})))
        check("tool: construction_guidelines", r["count"] >= 8, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("construction_approvals", {"project_type": "apartment"})))
        check("tool: construction_approvals", r["step_count"] >= 5, str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("construction_qa", {"stage": "structure"})))
        check("tool: construction_qa", r.get("stage") == "structure" and len(r.get("checks", [])) >= 3,
              str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("construction_hse", {})))
        check("tool: construction_hse", r["count"] >= 5, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("construction_trades", {})))
        check("tool: construction_trades", r["count"] >= 8, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("construction_estimate_save", {
            "title": "Integration test house", "covered_area": 1500, "floors": 1})))
        STATE["est_id"] = r.get("saved", {}).get("id")
        check("tool: construction_estimate_save", bool(STATE["est_id"]) and r["saved"]["total_cost"] > 0,
              str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("construction_estimates", {})))
        check("tool: construction_estimates", r["count"] >= 1, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("construction_estimate_get",
                                                      {"estimate_id": STATE["est_id"]})))
        check("tool: construction_estimate_get", r.get("id") == STATE["est_id"], str(r.get("error")))

        html = text_of(await client.call_tool("construction_portal", {"lang": "en"}))
        check("tool: construction_portal (EN)", "Construction wing" in html and "cc-out" in html,
              str(len(html)))
        html_ur = text_of(await client.call_tool("construction_portal", {"lang": "ur", "theme": "dark"}))
        check("tool: construction_portal (UR/RTL)", "تعمیرات" in html_ur and 'dir="rtl"' in html_ur,
              str(len(html_ur)))

        html = text_of(await client.call_tool("construction_report", {"covered_area": 2000}))
        check("tool: construction_report", "Element build-up" in html and "__" not in html, str(len(html)))

        # ---------------- maintenance ----------------
        r = json.loads(text_of(await client.call_tool("maintenance_overview", {})))
        check("tool: maintenance_overview", r["counts"]["components"] >= 10, str(r["counts"]))

        r = json.loads(text_of(await client.call_tool("maintenance_components", {})))
        check("tool: maintenance_components", r["count"] >= 10, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("maintenance_component", {"key": "hvac"})))
        check("tool: maintenance_component", r.get("key") == "hvac", str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("maintenance_services", {"emergency": True})))
        check("tool: maintenance_services (emergency)", r["count"] >= 3, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("maintenance_service", {"key": "ac_service"})))
        check("tool: maintenance_service", r.get("key") == "ac_service", str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("maintenance_defects", {"severity": "high"})))
        check("tool: maintenance_defects (high)", r["count"] >= 3, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("maintenance_defect", {"key": "roof_seepage"})))
        check("tool: maintenance_defect", r.get("key") == "roof_seepage", str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("maintenance_estimate", {
            "covered_area": 2000, "property_type": "house", "tier": "standard", "age_years": 8})))
        check("tool: maintenance_estimate", r["annual"]["total"] > 0 and len(r["category_breakdown"]) >= 5,
              str(r.get("error")))
        check("tool: maintenance_estimate reserve", r["reserve"]["annual_reserve"] > 0, "")

        r = json.loads(text_of(await client.call_tool("maintenance_schedule", {"horizon_months": 12})))
        check("tool: maintenance_schedule", r["task_count"] > 0 and len(r["by_month"]) == 12,
              str(r["task_count"]))

        r = json.loads(text_of(await client.call_tool("maintenance_lifecycle", {
            "covered_area": 4000, "property_type": "apartment", "age_years": 5, "years": 30})))
        check("tool: maintenance_lifecycle", r["total_replacement_cost"] > 0 and len(r["replacements"]) > 0,
              str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("maintenance_reserve", {"covered_area": 2000})))
        check("tool: maintenance_reserve", r["annual_reserve"] > 0 and len(r["components"]) >= 10,
              str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("maintenance_condition", {"age_years": 5})))
        check("tool: maintenance_condition", r["score"] > 0 and r["band"] in
              ("excellent", "good", "fair", "poor", "critical"), str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("maintenance_repair_estimate",
                                                      {"defect": "roof_seepage", "quantity": 300})))
        check("tool: maintenance_repair_estimate", r["cost_mid"] > 0 and r["cost_low"] < r["cost_high"],
              str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("maintenance_repair_or_replace", {
            "component": "roof_waterproofing", "age_years": 9, "covered_area": 2000})))
        check("tool: maintenance_repair_or_replace", r["decision"] in ("repair", "replace"),
              str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("maintenance_impact", {
            "market_value": 12000000, "monthly_rent": 90000, "current_condition": "deferred"})))
        check("tool: maintenance_impact", r["value_uplift"] > 0 and r["annual_rent_uplift"] > 0,
              str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("maintenance_guidelines", {})))
        check("tool: maintenance_guidelines", r["count"] >= 5, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("maintenance_warranty", {"component": "roof_waterproofing"})))
        check("tool: maintenance_warranty", r.get("years", 0) > 0, str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("maintenance_inspection", {"area": "mep"})))
        check("tool: maintenance_inspection", len(r.get("checks", [])) >= 3, str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("maintenance_plan_save", {
            "title": "Integration AMC", "covered_area": 2500, "property_type": "house", "age_years": 10})))
        STATE["plan_id"] = r.get("saved", {}).get("id")
        check("tool: maintenance_plan_save", bool(STATE["plan_id"]) and r["saved"]["annual_cost"] > 0,
              str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("maintenance_plans", {})))
        check("tool: maintenance_plans", r["count"] >= 1, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("maintenance_plan_get", {"plan_id": STATE["plan_id"]})))
        check("tool: maintenance_plan_get", r.get("id") == STATE["plan_id"], str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("maintenance_work_order_create", {
            "title": "Integration work order", "component": "plumbing",
            "defect": "plumbing_leak", "priority": "urgent", "estimated_cost": 9000})))
        STATE["wo_id"] = r.get("id")
        check("tool: maintenance_work_order_create", bool(STATE["wo_id"]) and r["status"] == "open",
              str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("maintenance_work_orders", {"priority": "urgent"})))
        check("tool: maintenance_work_orders (urgent)", r["count"] >= 1, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("maintenance_work_order_get", {"wo_id": STATE["wo_id"]})))
        check("tool: maintenance_work_order_get", r.get("id") == STATE["wo_id"], str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("maintenance_work_order_update", {
            "wo_id": STATE["wo_id"], "status": "in_progress", "assignee": "plumber-1"})))
        check("tool: maintenance_work_order_update", r.get("status") == "in_progress", str(r.get("error")))

        html = text_of(await client.call_tool("maintenance_portal", {"lang": "en"}))
        check("tool: maintenance_portal (EN)", "Maintenance wing" in html and "mc-out" in html, str(len(html)))
        html_ur = text_of(await client.call_tool("maintenance_portal", {"lang": "ur"}))
        check("tool: maintenance_portal (UR)", "دیکھ بھال" in html_ur, str(len(html_ur)))

        html = text_of(await client.call_tool("maintenance_report", {
            "covered_area": 2000, "property_type": "apartment", "age_years": 8}))
        check("tool: maintenance_report", "Maintenance summary" in html and "__" not in html, str(len(html)))

        # ---------------- wing resources & prompts ----------------
        for uri, needle in (("construction://overview", "counts"),
                            ("construction://techniques", "techniques"),
                            ("construction://materials", "materials"),
                            ("construction://element-rates", "elements"),
                            ("construction://guidelines", "guidelines"),
                            ("construction://approvals", "steps"),
                            ("construction://trades", "trades"),
                            ("maintenance://overview", "counts"),
                            ("maintenance://components", "components"),
                            ("maintenance://services", "services"),
                            ("maintenance://defects", "defects"),
                            ("maintenance://guidelines", "guidelines"),
                            ("maintenance://warranty", "terms"),
                            ("maintenance://condition-scale", "scale")):
            body = await client.read_resource(uri)
            uri_text = "".join(getattr(c, "text", "") for c in body.contents)
            check(f"resource: {uri}", needle in uri_text, uri_text[:70].replace("\n", " "))

        for uri, needle in (("construction://technique/rcc_frame", "rcc_frame"),
                            ("maintenance://component/hvac", "hvac"),
                            ("maintenance://defect/roof_seepage", "seepage")):
            body = await client.read_resource(uri)
            uri_text = "".join(getattr(c, "text", "") for c in body.contents)
            check(f"resource template: {uri}", needle in uri_text, uri_text[:70].replace("\n", " "))

        for pname, pargs in (("construction_estimate_prompt", {"building_type": "house"}),
                             ("construction_advisory_prompt", {"city": "Lahore"}),
                             ("maintenance_plan_prompt", {"property_type": "apartment"}),
                             ("maintenance_incident_prompt", {"symptom": "damp ceiling"})):
            prompt = await client.get_prompt(pname, pargs)
            check(f"prompt: {pname}", len(prompt.messages) > 0, str(len(prompt.messages)))


# ============================================================
# 2) FastAPI / REST
# ============================================================


_GUARDED = ("/crm", "/marketing", "/broker", "/agents", "/messaging", "/cities", "/schemes", "/blocks", "/admin/basedata")


def _sign_in_guarded(client: TestClient) -> str:
    """The CRM family needs a signed-in user: add the seeded admin's token to those calls unless a
    check passes its own Authorization header (negative checks pass an empty one)."""
    token = client.post("/auth/login", json={"identifier": "admin@portal.pk", "password": "Admin@12345"}).json()["token"]
    plain = client.request

    def request(method: str, url: Any, *args: Any, **kwargs: Any) -> Any:
        if str(url).startswith(_GUARDED):
            headers = dict(kwargs.get("headers") or {})
            headers.setdefault("Authorization", f"Bearer {token}")
            kwargs["headers"] = headers
        return plain(method, url, *args, **kwargs)

    client.request = request  # type: ignore[method-assign]
    STATE["admin_token"] = token
    return token


def run_access_checks(client: TestClient) -> None:
    """Sign-in and roles on the CRM family (access.py)."""
    anon = {"Authorization": ""}

    def login(ident: str, pw: str) -> Dict[str, str]:
        return {"Authorization": "Bearer " + client.post("/auth/login", json={"identifier": ident, "password": pw}).json()["token"]}

    check("access: GET /crm/leads without sign-in -> 401", client.get("/crm/leads", headers=anon).status_code == 401)
    check("access: GET /crm/insights without sign-in -> 401", client.get("/crm/insights", headers=anon).status_code == 401)
    check("access: GET /messaging/overview without sign-in -> 401", client.get("/messaging/overview", headers=anon).status_code == 401)
    r = client.get("/crm/agents", headers=anon)
    check("access: public agent card has contact fields only", r.status_code == 200
          and "commission_rate" not in r.json()["agents"][0] and "phone" in r.json()["agents"][0], str(r.status_code))
    r = client.post("/crm/leads", headers=anon, json={"name": "Portal visitor", "phone": "03001112233", "source": "website"})
    check("access: public enquiry (POST /crm/leads) still works", r.status_code == 201, str(r.status_code))
    check("access: AI Hub catalogue is public", client.get("/agents/catalog", headers=anon).status_code == 200)
    check("access: agent tools need sign-in", client.get("/agents/smart-actions", headers=anon).status_code == 401)
    buyer = login("bilal@example.com", "Buyer@12345")
    check("access: buyer has no CRM role -> 403", client.get("/crm/leads", headers=buyer).status_code == 403)
    me = client.get("/auth/me", headers=buyer).json()["user"]["id"]
    check("access: messaging - own unread summary", client.get(f"/messaging/unread-summary/{me}", headers=buyer).status_code == 200)
    check("access: messaging - someone else's -> 403", client.get("/messaging/unread-summary/not-me", headers=buyer).status_code == 403)
    r = client.post("/messaging/presence", headers=buyer, json={"user_id": "not-me", "status": "online"})
    check("access: messaging - acting as another user -> 403", r.status_code == 403, str(r.status_code))
    agent = login("agent@portal.pk", "Agent@12345")
    aid = client.get("/auth/me", headers=agent).json()["user"].get("agent_id")
    leads = client.get("/crm/leads", headers=agent).json().get("leads", [])
    check("access: demo agent is linked to a CRM agent", bool(aid))
    check("access: agent sees only own leads", bool(leads) and all(x.get("assigned_agent_id") == aid for x in leads), str(len(leads)))
    other = next((x for x in core.leads_db if x.assigned_agent_id != aid), None)
    check("access: agent can't open another agent's lead", other is not None and client.get(f"/crm/leads/{other.id}", headers=agent).status_code == 403)
    check("access: agent can't brief another agent's lead", other is not None and client.post(f"/crm/ai/lead-brief/{other.id}", headers=agent).status_code == 403)
    ins = client.get("/crm/insights", headers=agent).json()
    check("access: agent insights cover own book", ins["kpis"]["leads_total"] == len(leads), str(ins["kpis"]["leads_total"]))
    # --- base data admin (basedata.manage)
    admin = login("admin@portal.pk", "Admin@12345")
    check("basedata: signed out -> 401", client.get("/admin/basedata", headers=anon).status_code == 401)
    check("basedata: agent -> 403", client.get("/admin/basedata", headers=agent).status_code == 403)
    ov = client.get("/admin/basedata", headers=admin).json()
    check("basedata: overview lists cities / schemes / blocks", [t["table"] for t in ov["tables"]] == ["cities", "schemes", "blocks"], str(ov)[:120])
    r = client.post("/admin/basedata/cities", headers=admin, json={"name": "Basedata Test City", "state": "Punjab", "population": 1000,
                                                                   "sources": [{"title": "t", "url": "https://example.com"}]})
    city_id = r.json().get("id")
    check("basedata: create city", r.status_code == 201 and bool(city_id), r.text[:120])
    check("basedata: duplicate name -> 422", client.post("/admin/basedata/cities", headers=admin, json={"name": "basedata test city"}).status_code == 422)
    check("basedata: bad type -> 422", client.put(f"/admin/basedata/cities/{city_id}", headers=admin, json={"population": "many"}).status_code == 422)
    r = client.put(f"/admin/basedata/cities/{city_id}", headers=admin, json={"population": 2000, "district": "Test"})
    check("basedata: update city", r.status_code == 200 and r.json().get("population") == 2000, r.text[:120])
    r = client.post("/admin/basedata/schemes", headers=admin, json={"name": "Basedata Test Scheme", "city_id": city_id, "approval_status": "approved", "plot_sizes": ["5 marla"]})
    scheme_id = r.json().get("id")
    check("basedata: create scheme", r.status_code == 201 and r.json().get("city") == "Basedata Test City", r.text[:120])
    check("basedata: bad approval status -> 422", client.post("/admin/basedata/schemes", headers=admin, json={"name": "X", "city_id": city_id, "approval_status": "maybe"}).status_code == 422)
    r = client.post("/admin/basedata/blocks", headers=admin, json={"name": "Block A", "scheme_id": scheme_id})
    check("basedata: create block", r.status_code == 201, r.text[:120])
    check("basedata: city in use -> 409", client.delete(f"/admin/basedata/cities/{city_id}", headers=admin).status_code == 409)
    check("basedata: scheme in use -> 409", client.delete(f"/admin/basedata/schemes/{scheme_id}", headers=admin).status_code == 409)
    check("basedata: delete block", client.delete(f"/admin/basedata/blocks/{r.json()['id']}", headers=admin).status_code == 200)
    check("basedata: delete scheme then city", client.delete(f"/admin/basedata/schemes/{scheme_id}", headers=admin).status_code == 200
          and client.delete(f"/admin/basedata/cities/{city_id}", headers=admin).status_code == 200)
    check("basedata: old write routes need the permission", client.put("/schemes/x", headers=agent, json={}).status_code == 403)
    check("basedata: public city list stays open", client.get("/cities", headers=anon).status_code == 200)

    support = login("support@portal.pk", "Support@12345")
    check("access: customer support sees the whole CRM", client.get("/crm/leads", headers=support).json()["count"] >= len(leads))


def run_fastapi_checks(mcp_lead_id: str | None, mcp_layer_id: str | None) -> None:
    print("\n=== FastAPI / REST ===")
    with TestClient(app) as client:
        _sign_in_guarded(client)
        run_access_checks(client)
        r = client.get("/health")
        check("GET /health", r.status_code == 200 and r.json().get("status") == "ok", str(r.status_code))

        r = client.get("/properties")
        check("GET /properties", r.status_code == 200 and r.json().get("count", 0) > 0, str(r.status_code))

        r = client.get("/search", params={"city": "Karachi", "use_type": "residential"})
        check("GET /search?city=Karachi", r.status_code == 200 and r.json().get("count", 0) > 0, str(r.status_code))

        r = client.get("/nearby", params={"lat": 24.8607, "lon": 67.0011, "radius_km": 20})
        check("GET /nearby", r.status_code == 200 and r.json().get("count", 0) > 0, str(r.status_code))

        r = client.get("/rag/search", params={"query": "commercial shop Lahore"})
        check("GET /rag/search", r.status_code == 200 and r.json().get("count", 0) > 0, str(r.status_code))

        r = client.get("/crm/dashboard")
        check("GET /crm/dashboard", r.status_code == 200 and r.json().get("leads", {}).get("total", 0) > 0, str(r.status_code))

        r = client.get("/crm/pipeline")
        check("GET /crm/pipeline", r.status_code == 200 and "stages" in r.json(), str(r.status_code))

        r = client.get("/bigprojects")
        check("GET /bigprojects", r.status_code == 200 and r.json().get("count", 0) > 0, str(r.status_code))

        r = client.get("/units/convert", params={"value": 10, "from_unit": "marla", "to_unit": "sqft"})
        check("GET /units/convert", r.status_code == 200 and r.json().get("result") == 2722.5, str(r.json()))

        # --- GIS endpoints ---
        r = client.get("/gis/base-maps")
        check("GET /gis/base-maps", r.status_code == 200 and r.json().get("count", 0) >= 5, str(r.status_code))

        r = client.get("/gis/master-plans")
        check("GET /gis/master-plans", r.status_code == 200 and r.json().get("count", 0) > 0, str(r.status_code))

        r = client.get("/gis/layers", params={"entity_type": "scheme"})
        check("GET /gis/layers?entity_type=scheme", r.status_code == 200 and r.json().get("count", 0) > 0, str(r.status_code))

        r = client.get("/gis/properties-in-bounds",
                       params={"south": 31.40, "west": 74.20, "north": 31.55, "east": 74.40})
        check("GET /gis/properties-in-bounds", r.status_code == 200 and r.json().get("count", 0) > 0, str(r.status_code))

        r = client.post("/gis/properties-in-polygon", json={
            "coordinates": [[31.40, 74.20], [31.40, 74.40], [31.55, 74.40], [31.55, 74.20]]})
        check("POST /gis/properties-in-polygon", r.status_code == 200 and r.json().get("count", 0) > 0, str(r.status_code))

        r = client.get("/gis/area", params={
            "coordinates": json.dumps([[31.4460, 74.2740], [31.4460, 74.2870], [31.4560, 74.2870], [31.4560, 74.2740]])})
        check("GET /gis/area", r.status_code == 200 and r.json().get("area_sqm", 0) > 0, str(r.status_code))

        # --- infrastructure mega projects & drawn study areas ---
        r = client.get("/geo/megaprojects")
        check("GET /geo/megaprojects", r.status_code == 200 and r.json().get("count", 0) >= 10, str(r.status_code))
        r = client.get("/geo/megaprojects", params={"type": "ring_road", "format": "geojson"})
        feats = r.json().get("features", []) if r.status_code == 200 else []
        check("GET /geo/megaprojects?format=geojson", bool(feats) and all(f["properties"]["type"] == "ring_road" for f in feats), str(r.status_code))
        r = client.get("/geo/megaprojects/near", params={"lat": 33.428, "lon": 72.995})
        check("GET /geo/megaprojects/near (Rawalpindi Ring Road)",
              r.status_code == 200 and any(p["id"] == "rawalpindi-ring-road" for p in r.json().get("projects", [])), str(r.status_code))
        r = client.get("/geo/megaprojects/no-such-project")
        check("GET /geo/megaprojects/{id} (404)", r.status_code == 404, str(r.status_code))

        # Road network: works with or without the built OpenStreetMap data file.
        r = client.get("/geo/roads", params={"south": 33.6, "west": 73.0, "north": 33.7, "east": 73.1, "zoom": 13})
        check("GET /geo/roads", r.status_code == 200 and "roads" in r.json(), str(r.status_code))
        r = client.get("/geo/roads/search", params={"q": "M-2"})
        check("GET /geo/roads/search", r.status_code == 200 and "roads" in r.json(), str(r.status_code))

        # Water bodies and districts: also work without the built OpenStreetMap files.
        r = client.get("/geo/water", params={"south": 33.9, "west": 72.5, "north": 34.2, "east": 72.9, "zoom": 11})
        check("GET /geo/water", r.status_code == 200 and "water" in r.json(), str(r.status_code))
        r = client.get("/geo/districts")
        check("GET /geo/districts", r.status_code == 200 and r.json().get("type") == "FeatureCollection", str(r.status_code))

        aois_before = len(core.aois_db)
        r = client.post("/geo/study-area", json={"kind": "circle", "center": [33.428, 72.995], "radius_m": 1500})
        body = r.json() if r.status_code == 200 else {}
        check("POST /geo/study-area (circle)",
              r.status_code == 200 and body.get("grade") in "ABCDE" and "infrastructure" in body.get("scores", {})
              and any(p["id"] == "rawalpindi-ring-road" for p in body.get("mega_projects", {}).get("projects", [])), str(r.status_code))
        check("POST /geo/study-area leaves no AOI behind", len(core.aois_db) == aois_before, str(len(core.aois_db)))
        r = client.post("/geo/study-area", json={"kind": "rectangle", "bounds": {"south": 31.44, "west": 74.27, "north": 31.46, "east": 74.29}})
        check("POST /geo/study-area (rectangle)", r.status_code == 200 and r.json().get("shape", {}).get("area_km2", 0) > 0, str(r.status_code))
        r = client.post("/geo/study-area", json={"kind": "rectangle", "coordinates": [[31.44, 74.27], [31.44, 74.29], [31.46, 74.29], [31.46, 74.27]]})
        check("POST /geo/study-area (rectangle, four corners)",
              r.status_code == 200 and r.json().get("shape", {}).get("kind") == "rectangle" and r.json()["shape"]["area_km2"] > 0, str(r.status_code))
        r = client.post("/geo/study-area", json={"kind": "polygon", "coordinates": [[31.44, 74.27], [31.46, 74.28]]})
        check("POST /geo/study-area (bad polygon -> 422)", r.status_code == 422, str(r.status_code))

        r = client.get("/gis/bearing", params={"lat1": 31.5204, "lon1": 74.3587, "lat2": 31.4504, "lon2": 74.2800})
        check("GET /gis/bearing", r.status_code == 200 and r.json().get("distance_km", 0) > 0, str(r.status_code))

        r = client.get("/gis/export/geojson/scheme/" + core.housing_schemes_db[0].id)
        check("GET /gis/export/geojson", r.status_code == 200 and r.json().get("type") == "FeatureCollection", str(r.status_code))

        r = client.get("/gis/export/kml/scheme/" + core.housing_schemes_db[0].id)
        check("GET /gis/export/kml", r.status_code == 200 and "<kml" in r.text
              and r.headers.get("content-type", "").startswith("application/vnd.google-earth.kml"), str(r.status_code))

        r = client.get("/gis/map/scheme/" + core.housing_schemes_db[0].id)
        check("GET /gis/map/{entity_type}/{entity_id}", r.status_code == 200 and "leaflet" in r.text.lower(), str(r.status_code))

        r = client.get("/gis/map/scheme/" + core.housing_schemes_db[0].id, params={"include_news": True})
        check("GET /gis/map (include_news)", r.status_code == 200 and "portal-ticker" in r.text, str(r.status_code))

        # --- create a layer over REST, confirm it lands in the shared core store ---
        r = client.post("/gis/layers", json={
            "name": "REST Test Layer",
            "entity_type": "city",
            "entity_id": core.cities_db[0].id,
            "layer_type": "boundary",
            "geojson": {"type": "FeatureCollection", "features": []},
        })
        check("POST /gis/layers", r.status_code == 201, f"{r.status_code} {r.text[:120]}")
        rest_layer_id = r.json().get("id") if r.status_code == 201 else None
        if rest_layer_id:
            check("shared store: REST layer present in core GIS store",
                  core.gis.find_layer(rest_layer_id) is not None)

        # --- MCP-created layer must be visible over REST (shared store) ---
        if mcp_layer_id:
            r = client.get(f"/gis/layers/{mcp_layer_id}")
            check("shared store: MCP layer visible over REST",
                  r.status_code == 200 and r.json().get("name") == "MCP Test Master Plan", str(r.status_code))

        # --- GIS analysis endpoints ---
        scheme_id = core.housing_schemes_db[0].id

        r = client.get("/gis/analysis/assumptions")
        check("GET /gis/analysis/assumptions", r.status_code == 200 and r.json().get("economic_multiplier", 0) > 0,
              str(r.status_code))

        r = client.post("/gis/buffer", json={"geometry": {"type": "Point", "coordinates": [74.28, 31.45]},
                                             "distance_m": 750})
        check("POST /gis/buffer", r.status_code == 200 and r.json().get("area_hectares", 0) > 0, str(r.status_code))

        r = client.post("/gis/buffers", json={"entity_type": "scheme", "entity_id": scheme_id,
                                              "name": "REST buffer", "distance_m": 900,
                                              "latitude": 31.4504, "longitude": 74.28})
        check("POST /gis/buffers", r.status_code == 201, f"{r.status_code} {r.text[:120]}")

        r = client.get("/gis/ring-analysis", params={"lat": 31.4504, "lon": 74.28, "radii_km": "1,3,5"})
        check("GET /gis/ring-analysis", r.status_code == 200 and len(r.json().get("rings", [])) == 3, str(r.status_code))

        r = client.post("/gis/polygon-analysis", json={
            "coordinates": [[31.40, 74.20], [31.40, 74.40], [31.55, 74.40], [31.55, 74.20]], "name": "Lahore box"})
        check("POST /gis/polygon-analysis", r.status_code == 200 and r.json().get("properties", {}).get("count", 0) > 0,
              str(r.status_code))

        r = client.get(f"/gis/analysis/scheme/{scheme_id}")
        check("GET /gis/analysis/{type}/{id}", r.status_code == 200
              and r.json().get("development_cost", {}).get("total", 0) > 0
              and r.json().get("economic_impact", {}).get("jobs_total", 0) > 0, str(r.status_code))

        r = client.get(f"/gis/analysis/scheme/{scheme_id}/cost")
        check("GET /gis/analysis/{type}/{id}/cost", r.status_code == 200
              and r.json().get("development_cost", {}).get("construction", 0) > 0, str(r.status_code))

        r = client.get(f"/gis/analysis/scheme/{scheme_id}/population")
        check("GET /gis/analysis/{type}/{id}/population", r.status_code == 200
              and r.json().get("population", {}).get("population_from_listings", 0) > 0, str(r.status_code))

        r = client.get(f"/gis/analysis/scheme/{scheme_id}/economic-impact")
        check("GET /gis/analysis/{type}/{id}/economic-impact", r.status_code == 200
              and r.json().get("economic_impact", {}).get("total_economic_output", 0) > 0, str(r.status_code))

        r = client.get(f"/gis/features/scheme/{scheme_id}", params={"metric": "population"})
        check("GET /gis/features/{scope}/{id}", r.status_code == 200 and r.json().get("count", 0) > 0, str(r.status_code))

        r = client.get(f"/gis/thematic/scheme/{scheme_id}", params={"metric": "market_value", "palette": "greens"})
        check("GET /gis/thematic/{scope}/{id}", r.status_code == 200 and "choropleth" in r.text, str(r.status_code))

        r = client.get(f"/gis/report/scheme/{scheme_id}")
        check("GET /gis/report/{type}/{id}", r.status_code == 200 and "Economic impact" in r.text, str(r.status_code))

        r = client.get(f"/gis/report/scheme/{scheme_id}", params={"include_outlook": True, "include_news": True})
        check("GET /gis/report (outlook+news)", r.status_code == 200 and "portal-ticker" in r.text
              and "Future predictions" in r.text, str(r.status_code))

        # --- cost/development, forecasting, outlook, news ---
        r = client.get(f"/gis/analysis/scheme/{scheme_id}/cost-development")
        check("GET /gis/analysis/.../cost-development", r.status_code == 200
              and r.json().get("cost_development", {}).get("gross_development_value", 0) > 0, str(r.status_code))

        r = client.get(f"/gis/analysis/scheme/{scheme_id}/factors")
        check("GET /gis/analysis/.../factors", r.status_code == 200
              and r.json().get("index", {}).get("composite", 0) > 0, str(r.status_code))

        r = client.get(f"/gis/analysis/scheme/{scheme_id}/forecast", params={"years": 5})
        check("GET /gis/analysis/.../forecast", r.status_code == 200
              and len(r.json().get("forecast", {}).get("scenarios", {})) == 4, str(r.status_code))

        r = client.get(f"/gis/analysis/scheme/{scheme_id}/scenarios")
        check("GET /gis/analysis/.../scenarios", r.status_code == 200
              and "expected" in r.json(), str(r.status_code))

        r = client.get(f"/gis/outlook/scheme/{scheme_id}")
        check("GET /gis/outlook/{type}/{id}", r.status_code == 200 and "portal-ticker" in r.text
              and "Future predictions" in r.text, str(r.status_code))

        r = client.get("/news")
        check("GET /news", r.status_code == 200 and r.json().get("count", 0) > 0, str(r.status_code))

        r = client.get("/news/channels")
        check("GET /news/channels", r.status_code == 200 and r.json().get("count", 0) > 3, str(r.status_code))

        r = client.get("/news/impact", params={"city": "Karachi"})
        check("GET /news/impact", r.status_code == 200
              and r.json().get("summary", {}).get("count", 0) > 0, str(r.status_code))

        r = client.get("/news/ticker.html", params={"city": "Lahore"})
        check("GET /news/ticker.html", r.status_code == 200 and "portal-ticker" in r.text, str(r.status_code))

        r = client.post("/news", json={"title": "REST test headline", "source": "Test Wire",
                                       "category": "policy", "sentiment": "negative"})
        check("POST /news", r.status_code == 201 and r.json().get("impact_score", 0) < 0, str(r.status_code))

        # --- create a property over REST, then read it back over REST ---
        r = client.post("/properties", json={
            "title": "REST Created Test House",
            "price": 33_000_000,
            "city_id": core.cities_db[0].id,
            "category": "house",
            "marla_area": 8,
            "bedrooms": 4,
        })
        check("POST /properties", r.status_code == 201, f"{r.status_code} {r.text[:120]}")
        created = r.json() if r.status_code == 201 else {}
        if created.get("id"):
            r2 = client.get(f"/properties/{created['id']}")
            check("GET /properties/{id} round-trip", r2.status_code == 200 and r2.json()["title"] == "REST Created Test House",
                  str(r2.status_code))

        # --- MCP-created lead must be visible over REST (shared store) ---
        if mcp_lead_id:
            r = client.get(f"/crm/leads/{mcp_lead_id}")
            check("shared store: MCP lead visible over REST", r.status_code == 200 and
                  r.json().get("lead", {}).get("name") == "MCP Created Lead", str(r.status_code))

        # --- convert that lead to a customer over REST ---
        if mcp_lead_id:
            r = client.post(f"/crm/leads/{mcp_lead_id}/convert", params={"customer_type": "buyer"})
            check("POST /crm/leads/{id}/convert", r.status_code == 200 and "customer" in r.json(), str(r.status_code))

        # --- create a lead over REST for cross-checking in MCP ---
        r = client.post("/crm/leads", json={"name": "REST Created Lead", "city_id": core.cities_db[1].id})
        check("POST /crm/leads", r.status_code == 201, f"{r.status_code} {r.text[:120]}")

        # --- OpenAI-compatible facade ---
        r = client.get("/v1/models")
        check("GET /v1/models", r.status_code == 200 and r.json().get("object") == "list"
              and len(r.json().get("data", [])) > 0, str(r.status_code))

        r = client.post("/v1/chat/completions", json={
            "model": "portal-realestate-rag",
            "messages": [{"role": "user", "content": "5 bedroom house in Lahore under 100,000,000"}],
        })
        body = r.json() if r.status_code == 200 else {}
        content = body.get("choices", [{}])[0].get("message", {}).get("content", "") if body else ""
        check("POST /v1/chat/completions", r.status_code == 200 and body.get("object") == "chat.completion"
              and len(content) > 0, f"{r.status_code} {r.text[:120]}")

        with client.stream("POST", "/v1/chat/completions", json={
            "model": "portal-realestate-rag",
            "stream": True,
            "messages": [{"role": "user", "content": "apartments in Karachi"}],
        }) as s:
            streamed = "".join(s.iter_text())
        check("POST /v1/chat/completions (stream)", s.status_code == 200
              and "chat.completion.chunk" in streamed and "[DONE]" in streamed, f"{s.status_code}")

        r = client.post("/v1/embeddings", json={"model": "portal-realestate-rag", "input": ["marla house Lahore"]})
        emb = r.json().get("data", [{}])[0].get("embedding", []) if r.status_code == 200 else []
        check("POST /v1/embeddings", r.status_code == 200 and len(emb) > 0, f"{r.status_code}")

        r = client.post("/v1/completions", json={"model": "portal-realestate-rag", "prompt": "plots in Islamabad"})
        check("POST /v1/completions", r.status_code == 200 and r.json().get("object") == "text_completion",
              str(r.status_code))

        # --- Authentication: OTP-verified signup, login, sessions, reset ---
        auth_email = "integration@portal.test"
        r = client.post("/auth/signup", json={
            "email": auth_email, "mobile": "0345 555 0101",
            "password": "Secret@123", "name": "Integration User",
        })
        body = r.json() if r.status_code == 201 else {}
        otps = (body.get("verification") or {}).get("dev_otp") or {}
        check("POST /auth/signup", r.status_code == 201 and body.get("otp_required") is True
              and body.get("status") == "pending" and len(otps) == 2, f"{r.status_code} {r.text[:100]}")

        r = client.post("/auth/login", json={"identifier": auth_email, "password": "Secret@123"})
        check("POST /auth/login (unverified -> 403)", r.status_code == 403
              and r.json()["detail"]["code"] == "otp_required", str(r.status_code))

        r = client.post("/auth/verify-otp", json={"identifier": auth_email, "code": "000000"})
        check("POST /auth/verify-otp (bad -> 400)", r.status_code == 400, str(r.status_code))

        r = client.post("/auth/verify-otp", json={"identifier": auth_email, "code": otps[auth_email]})
        verified = r.json() if r.status_code == 200 else {}
        auth_token = verified.get("token", "")
        check("POST /auth/verify-otp (activates + token)", r.status_code == 200
              and verified.get("verified") is True and verified.get("user", {}).get("status") == "active"
              and bool(auth_token), str(r.status_code))

        r = client.get("/auth/me", headers={"Authorization": f"Bearer {auth_token}"})
        check("GET /auth/me (bearer)", r.status_code == 200
              and r.json().get("user", {}).get("email") == auth_email, str(r.status_code))

        r = client.get("/auth/me")
        check("GET /auth/me (no token -> 401)", r.status_code == 401, str(r.status_code))

        r = client.post("/auth/login", json={"identifier": "03455550101", "password": "Secret@123"})
        check("POST /auth/login (mobile identifier)", r.status_code == 200 and bool(r.json().get("token")),
              str(r.status_code))

        r = client.post("/auth/login", json={"identifier": auth_email, "password": "wrong"})
        check("POST /auth/login (bad password -> 401)", r.status_code == 401, str(r.status_code))

        r = client.post("/auth/otp/request", json={"identifier": auth_email})
        lcode = r.json().get("dev_otp")
        r = client.post("/auth/otp/verify", json={"identifier": auth_email, "code": lcode})
        check("POST /auth/otp/verify (passwordless)", r.status_code == 200 and bool(r.json().get("token")),
              str(r.status_code))

        r = client.post("/auth/password/reset-request", json={"identifier": auth_email})
        rcode = r.json().get("dev_otp")
        r = client.post("/auth/password/reset", json={"identifier": auth_email, "code": rcode,
                                                      "new_password": "Newer@12345"})
        check("POST /auth/password/reset", r.status_code == 200 and r.json().get("reset") is True, str(r.status_code))

        r = client.get("/auth/me", headers={"Authorization": f"Bearer {auth_token}"})
        check("session revoked after reset -> 401", r.status_code == 401, str(r.status_code))

        r = client.post("/auth/login", json={"identifier": auth_email, "password": "Newer@12345"})
        token2 = r.json().get("token", "")
        r = client.post("/auth/refresh", headers={"Authorization": f"Bearer {token2}"})
        check("POST /auth/refresh", r.status_code == 200 and bool(r.json().get("token")), str(r.status_code))

        r = client.get("/auth/users")
        check("GET /auth/users (no token -> 401)", r.status_code == 401, str(r.status_code))

        r = client.get("/auth/config")
        check("GET /auth/config", r.status_code == 200 and r.json().get("otp_length") == 6, str(r.status_code))

        r = client.get("/auth/notifications")
        check("GET /auth/notifications", r.status_code == 200
              and len(r.json().get("notifications", [])) > 0, str(r.status_code))

        r = client.post("/auth/login", json={"identifier": "admin@portal.pk", "password": "Admin@12345"})
        check("POST /auth/login (seeded admin)", r.status_code == 200, str(r.status_code))

        # --- Portable app: passwordless signup, my listings, photos, CORS, AI helpers ---
        r = client.post("/auth/signup", json={"mobile": "0333 555 0199", "name": "App Seller", "role": "seller"})
        sent = (r.json().get("verification") or {}) if r.status_code == 201 else {}
        check("POST /auth/signup (passwordless)", r.status_code == 201 and len(sent.get("sent_to", [])) == 1,
              f"{r.status_code} {r.text[:100]}")
        ident = sent.get("sent_to", [""])[0]
        r = client.post("/auth/verify-otp", json={"identifier": ident, "code": (sent.get("dev_otp") or {}).get(ident, "")})
        seller_token = r.json().get("token", "") if r.status_code == 200 else ""
        check("passwordless signup -> token", bool(seller_token), str(r.status_code))
        check("signup reports delivery (simulated without providers)",
              sent.get("delivery", {}).get(ident) == "simulated", str(sent.get("delivery")))
        r = client.get("/auth/config")
        check("GET /auth/config delivery summary", r.json().get("delivery") == {"email": "simulated", "sms": "simulated"},
              str(r.json().get("delivery")))
        sh = {"Authorization": f"Bearer {seller_token}"}

        r = client.get("/me/listings")
        check("GET /me/listings (no token -> 401)", r.status_code == 401, str(r.status_code))
        city_id = client.get("/cities").json()["cities"][0]["id"]
        r = client.post("/me/listings", headers=sh, json={"title": "App 10 Marla House", "price": 45_000_000,
                                                          "city_id": city_id, "marla_area": 10})
        mine = r.json() if r.status_code == 201 else {}
        check("POST /me/listings (owned)", r.status_code == 201 and bool(mine.get("owner_user_id")), str(r.status_code))
        r = client.get("/me/listings", headers=sh)
        check("GET /me/listings", r.status_code == 200 and r.json().get("count") == 1, str(r.status_code))
        r = client.put(f"/me/listings/{mine.get('id')}", headers=sh, json={"status": "sold"})
        check("PUT /me/listings/{id}", r.status_code == 200 and r.json().get("status") == "sold", str(r.status_code))
        buyer_token = client.post("/auth/login", json={"identifier": "bilal@example.com",
                                                       "password": "Buyer@12345"}).json().get("token", "")
        r = client.put(f"/me/listings/{mine.get('id')}", headers={"Authorization": f"Bearer {buyer_token}"},
                       json={"status": "active"})
        check("PUT /me/listings/{id} (not owner -> 403)", r.status_code == 403, str(r.status_code))
        r = client.post(f"/me/listings/{mine.get('id')}/photos", headers=sh,
                        json={"data_url": "data:image/jpeg;base64," + _photo_jpeg_b64(), "is_primary": True})
        photo = r.json() if r.status_code == 201 else {}
        check("POST /me/listings/{id}/photos", r.status_code == 201
              and photo.get("image_urls", [""])[0] == photo.get("url"), str(r.status_code))
        r = client.get(photo.get("url", "/media/uploads/missing.jpg"))
        check("GET /media/uploads/{file}", r.status_code == 200 and r.headers["content-type"] == "image/jpeg",
              str(r.status_code))
        r = client.post(f"/me/listings/{mine.get('id')}/photos", headers=sh, json={"data_url": "aGVsbG8="})
        check("POST /me/listings/{id}/photos (not an image -> 415)", r.status_code == 415, str(r.status_code))
        if photo.get("url"):
            os.remove(os.path.join(os.path.dirname(os.path.abspath(__file__)), photo["url"].lstrip("/")))
        r = client.delete(f"/me/listings/{mine.get('id')}", headers=sh)
        check("DELETE /me/listings/{id}", r.status_code == 200 and r.json().get("deleted") is True, str(r.status_code))

        r = client.options("/me/listings", headers={"Origin": "capacitor://localhost",
                                                     "Access-Control-Request-Method": "POST",
                                                     "Access-Control-Request-Headers": "authorization"})
        check("CORS preflight", r.status_code == 200 and r.headers.get("access-control-allow-origin") == "*",
              str(r.status_code))
        r = client.get("/ai/capabilities")
        check("GET /ai/capabilities", r.status_code == 200 and r.json().get("chat_mode") in ("local", "upstream"),
              str(r.status_code))
        voice = r.json().get("voice") or {}
        check("GET /ai/capabilities voice status", {"provider", "stt", "tts", "realtime"} <= set(voice), str(voice))
        r = client.get("/ai/tools")
        names = [t["function"]["name"] for t in r.json().get("tools", [])] if r.status_code == 200 else []
        check("GET /ai/tools (chat tool definitions)",
              names == ["search_listings", "get_listing", "request_call", "find_places", "area_info", "master_plan",
                        "show_plan", "show_map", "web_lookup", "my_listings", "draft_listing"], str(names))
        r = client.get("/search", params={"min_bathrooms": 6, "limit": 50})
        baths = [x.get("bathrooms") for x in r.json().get("results", [])] if r.status_code == 200 else []
        check("GET /search?min_bathrooms=6", bool(baths) and all((b or 0) >= 6 for b in baths), str(baths))
        r = client.get("/search", params={"near": "school", "limit": 50})
        hits = [x.get("nearby") or {} for x in r.json().get("results", [])] if r.status_code == 200 else []
        check("GET /search?near=school (school within 2 km, closest first)",
              bool(hits) and all(h.get("category") == "education" and h.get("distance_km", 99) <= 2 for h in hits)
              and [h["distance_km"] for h in hits] == sorted(h["distance_km"] for h in hits), str(hits[:3]))
        r = client.get("/search", params={"near": "masjid", "near_km": 0.5})
        cats = {(x.get("nearby") or {}).get("category") for x in r.json().get("results", [])}
        check("GET /search?near=masjid (Urdu word -> mosque)", r.status_code == 200 and cats == {"worship"}, str(cats))
        r = client.get("/search", params={"feature": "solar"})
        titles = [x["title"] for x in r.json().get("results", [])]
        check("GET /search?feature=solar (listing amenities)", titles == ["Modern 10 Marla House"], str(titles))
        modern = next((x for x in client.get("/search", params={"limit": 50}).json()["results"]
                       if x["title"] == "Modern 10 Marla House"), None)
        r = client.get(f"/properties/{modern['id']}/nearby") if modern else None
        kinds = [n["category"] for n in r.json().get("nearby", [])] if r is not None and r.status_code == 200 else []
        check("GET /properties/{id}/nearby", {"education", "worship", "health", "shopping"} <= set(kinds), str(kinds))
        run_geo_checks(client)
        r = client.get("/properties/does-not-exist/nearby")
        check("GET /properties/{id}/nearby (unknown -> 404)", r.status_code == 404, str(r.status_code))
        if not voice.get("provider"):  # no OPENAI_API_KEY in the test environment
            r = client.post("/ai/transcribe", json={"audio_base64": "AAAA"})
            check("POST /ai/transcribe (no OpenAI key -> 501)", r.status_code == 501, str(r.status_code))
            r = client.post("/ai/speak", json={"text": "Assalam-o-Alaikum"})
            check("POST /ai/speak (no OpenAI key -> 501)", r.status_code == 501, str(r.status_code))
            r = client.post("/ai/realtime/session", json={"reply_lang": "ur"})
            check("POST /ai/realtime/session (no OpenAI key -> 501)", r.status_code == 501, str(r.status_code))
        run_ai_guard_checks()

        # --- MCP share the same auth store as REST ---
        r = client.post("/auth/login", json={"identifier": "mcp@portal.test", "password": "Secret@123"})
        check("shared store: MCP-created user can REST login", r.status_code == 200, str(r.status_code))

        # --- dual-language + light/dark theme facilities ---
        scheme_id = core.housing_schemes_db[0].id
        r = client.get(f"/gis/report/scheme/{scheme_id}", params={"lang": "ur", "theme": "dark", "include_outlook": True})
        check("GET /gis/report (ur + dark)", r.status_code == 200 and 'dir="rtl"' in r.text
              and 'html[data-theme="dark"]' in r.text and "آبادی" in r.text, str(r.status_code))

        r = client.get(f"/gis/report/scheme/{scheme_id}", headers={"Accept-Language": "ur-PK,en;q=0.8"})
        check("Accept-Language defaults the UI language", r.status_code == 200 and 'dir="rtl"' in r.text,
              str(r.status_code))

        r = client.get(f"/gis/report/scheme/{scheme_id}")
        check("report defaults to English/LTR", r.status_code == 200 and 'dir="ltr"' in r.text, str(r.status_code))

        r = client.get(f"/gis/outlook/scheme/{scheme_id}", params={"lang": "ur", "theme": "light"})
        check("GET /gis/outlook (ur)", r.status_code == 200 and 'dir="rtl"' in r.text
              and "Investment Outlook" not in r.text.split("<h1>")[1][:200], str(r.status_code))

        r = client.get(f"/gis/map/scheme/{scheme_id}", params={"include_news": True, "lang": "ur", "theme": "dark"})
        check("GET /gis/map (ur + dark + ticker)", r.status_code == 200 and 'dir="rtl"' in r.text
              and 'html[data-theme="dark"]' in r.text and "رئیل اسٹیٹ خبریں" in r.text, str(r.status_code))

        r = client.get(f"/gis/thematic/city/{core.cities_db[0].id}", params={"lang": "ur"})
        check("GET /gis/thematic (ur)", r.status_code == 200 and 'dir="rtl"' in r.text, str(r.status_code))

        r = client.get("/news/ticker", params={"city": "Lahore", "lang": "ur"})
        check("GET /news/ticker (ur/RTL label)", r.status_code == 200
              and 'dir="rtl"' in r.text and "رئیل اسٹیٹ خبریں" in r.text, str(r.status_code))

        r = client.get("/news/ticker.html", params={"lang": "ur", "theme": "light"})
        check("GET /news/ticker.html (ur/light)", r.status_code == 200 and 'dir="rtl"' in r.text
              and "html[data-theme=\"light\"]" in r.text, str(r.status_code))

        r = client.get("/i18n/languages")
        check("GET /i18n/languages", r.status_code == 200
              and [l["code"] for l in r.json()["languages"]] == ["en", "ur"], str(r.status_code))

        r = client.get("/i18n/strings/ur")
        check("GET /i18n/strings/ur", r.status_code == 200 and r.json()["count"] > 50, str(r.status_code))

        r = client.get("/ui/themes")
        check("GET /ui/themes", r.status_code == 200
              and [t["code"] for t in r.json()["themes"]] == ["auto", "light", "dark"], str(r.status_code))

        r = client.get(f"/gis/map/scheme/{scheme_id}", params={"lang": "zz", "theme": "nonsense"})
        check("unknown lang/theme fall back safely", r.status_code == 200 and 'dir="ltr"' in r.text, str(r.status_code))

        # --- accounting + finance (ROI) over REST ---
        r = client.get("/accounting/info")
        check("GET /accounting/info", r.status_code == 200 and r.json().get("counts", {}).get("accounts", 0) > 30,
              str(r.status_code))

        r = client.get("/accounting/trial-balance")
        check("GET /accounting/trial-balance", r.status_code == 200 and r.json().get("balanced") is True, str(r.status_code))

        r = client.get("/accounting/balance-sheet")
        check("GET /accounting/balance-sheet", r.status_code == 200
              and r.json().get("balanced") is True and r.json().get("total_assets", 0) > 0, str(r.status_code))

        r = client.get("/accounting/dashboard")
        check("GET /accounting/dashboard", r.status_code == 200 and r.json().get("total_assets", 0) > 0, str(r.status_code))

        r = client.get("/accounting/rent-roll")
        check("GET /accounting/rent-roll", r.status_code == 200 and r.json().get("monthly_rent", 0) > 0, str(r.status_code))

        r = client.get("/accounting/aging")
        check("GET /accounting/aging", r.status_code == 200 and len(r.json().get("buckets", {})) == 5, str(r.status_code))

        r = client.post("/accounting/journal", json={"lines": [
            {"account": "1010", "debit": 2500}, {"account": "4030", "credit": 2500}], "memo": "REST journal"})
        journal_body = r.json() if r.status_code == 201 else {}
        journal_lines = journal_body.get("lines", [])
        check("POST /accounting/journal", r.status_code == 201 and bool(journal_body.get("id"))
              and abs(sum(l.get("debit", 0) for l in journal_lines)
                      - sum(l.get("credit", 0) for l in journal_lines)) < 0.01,
              f"{r.status_code} {r.text[:120]}")

        r = client.post("/accounting/invoices", json={
            "counterparty": "REST Buyer", "invoice_type": "receivable",
            "lines": [{"description": "Rent", "amount": 120000}], "auto_post": True})
        rest_invoice = r.json() if r.status_code == 201 else {}
        check("POST /accounting/invoices", r.status_code == 201 and bool(rest_invoice.get("id")),
              f"{r.status_code} {r.text[:120]}")

        r = client.post("/accounting/payments", json={"amount": 50000, "counterparty": "REST Buyer"})
        check("POST /accounting/payments", r.status_code == 201 and bool(r.json().get("payment", {}).get("id")),
              f"{r.status_code} {r.text[:120]}")

        r = client.post("/accounting/expenses", json={"amount": 15000, "account_code": "5020", "category": "maintenance"})
        check("POST /accounting/expenses", r.status_code == 201, f"{r.status_code} {r.text[:120]}")

        r = client.get("/accounting/budgets")
        check("GET /accounting/budgets", r.status_code == 200 and r.json().get("count", 0) > 0, str(r.status_code))

        r = client.get("/finance/mortgage", params={"principal": 8_000_000})
        check("GET /finance/mortgage", r.status_code == 200 and r.json().get("payment", 0) > 0, str(r.status_code))

        r = client.post("/finance/investment-metrics", json={"cashflows": [-1_000_000, 300_000, 400_000, 500_000]})
        check("POST /finance/investment-metrics", r.status_code == 200 and r.json().get("irr") is not None, str(r.status_code))

        r = client.post("/finance/property-roi", json={"purchase_price": 20_000_000, "annual_rent": 1_800_000})
        check("POST /finance/property-roi", r.status_code == 200 and r.json().get("gross_rental_yield", 0) > 0,
              str(r.status_code))

        r = client.get("/finance/portfolio-roi")
        check("GET /finance/portfolio-roi", r.status_code == 200 and r.json().get("market_value", 0) > 0, str(r.status_code))

        r = client.get("/accounting/properties/" + core.properties_db[0].id + "/performance")
        check("GET /accounting/properties/{id}/performance", r.status_code == 200 and "profit_and_loss" in r.json(),
              str(r.status_code))

        # --- POI over REST ---
        r = client.post("/poi", json={"name": "REST test bank", "latitude": 31.4510, "longitude": 74.2820,
                                      "category": "bank"})
        check("POST /poi", r.status_code == 201 and bool(r.json().get("id")), f"{r.status_code} {r.text[:120]}")

        r = client.get("/poi")
        check("GET /poi", r.status_code == 200 and r.json().get("count", 0) > 0, str(r.status_code))

        r = client.get("/poi/categories")
        check("GET /poi/categories", r.status_code == 200 and r.json().get("count", 0) > 0, str(r.status_code))

        r = client.get("/poi/nearby", params={"latitude": 31.4504, "longitude": 74.2810, "radius_km": 3})
        check("GET /poi/nearby", r.status_code == 200 and r.json().get("count", 0) > 0, str(r.status_code))

        r = client.get("/poi/accessibility", params={"latitude": 31.4504, "longitude": 74.2810})
        check("GET /poi/accessibility", r.status_code == 200 and r.json().get("score", 0) > 0, str(r.status_code))

        r = client.get("/poi/map", params={"entity_type": "scheme", "entity_id": scheme_id})
        check("GET /poi/map", r.status_code == 200 and "leaflet" in r.text.lower(), str(r.status_code))

        r = client.post("/poi/within-polygon", json={
            "coordinates": [[31.40, 74.20], [31.40, 74.40], [31.55, 74.40], [31.55, 74.20]]})
        check("POST /poi/within-polygon", r.status_code == 200 and r.json().get("count", 0) > 0, str(r.status_code))

        # --- shared store: MCP-created POI visible over REST ---
        if STATE.get("poi_id"):
            r = client.get("/poi", params={"query": "MCP test clinic"})
            check("shared store: MCP POI visible over REST", r.status_code == 200
                  and any(p["id"] == STATE["poi_id"] for p in r.json().get("pois", [])), str(r.status_code))

        # --- AOI over REST ---
        r = client.post("/aoi", json={"name": "REST Test AOI", "kind": "circle", "center_latitude": 31.4504,
                                      "center_longitude": 74.2810, "radius_m": 900})
        rest_aoi = r.json() if r.status_code == 201 else {}
        check("POST /aoi", r.status_code == 201 and bool(rest_aoi.get("id")), f"{r.status_code} {r.text[:120]}")

        r = client.get("/aoi")
        check("GET /aoi", r.status_code == 200 and r.json().get("count", 0) > 0, str(r.status_code))

        if rest_aoi.get("id"):
            r = client.get(f"/aoi/{rest_aoi['id']}/analyze")
            check("GET /aoi/{id}/analyze", r.status_code == 200
                  and r.json().get("forecast", {}).get("composite_index", 0) > 0, str(r.status_code))

            r = client.get(f"/aoi/{rest_aoi['id']}/watch")
            check("GET /aoi/{id}/watch", r.status_code == 200 and "summary" in r.json(), str(r.status_code))

            r = client.get(f"/aoi/{rest_aoi['id']}/map")
            check("GET /aoi/{id}/map", r.status_code == 200 and "leaflet" in r.text.lower(), str(r.status_code))

            r = client.get(f"/aoi/{rest_aoi['id']}/report", params={"lang": "ur", "theme": "dark"})
            check("GET /aoi/{id}/report (ur/dark)", r.status_code == 200 and 'dir="rtl"' in r.text, str(r.status_code))

        r = client.post("/aoi/compare", json={"aoi_ids": [a.id for a in core.aois_db[:2]]})
        check("POST /aoi/compare", r.status_code == 200 and r.json().get("count", 0) >= 1, str(r.status_code))

        # --- portal discovery over REST ---
        r = client.get("/portal/health")
        check("GET /portal/health", r.status_code == 200 and r.json().get("status") == "ok", str(r.status_code))

        r = client.get("/portal/catalog")
        check("GET /portal/catalog", r.status_code == 200 and r.json().get("tool_count", 0) > 200, str(r.status_code))

        r = client.get("/portal/schema", params={"model": "invoice"})
        check("GET /portal/schema", r.status_code == 200 and "properties" in r.json().get("schema", {}), str(r.status_code))

        r = client.get("/portal/settings")
        check("GET /portal/settings", r.status_code == 200 and "forecast" in r.json(), str(r.status_code))

        r = client.put("/portal/settings", json={"updates": {"assumptions": {"occupancy_rate": 0.9}}})
        check("PUT /portal/settings", r.status_code == 200
              and r.json().get("updated", {}).get("assumptions.occupancy_rate") == 0.9, str(r.status_code))

        r = client.get("/portal/search", params={"query": "lahore"})
        check("GET /portal/search", r.status_code == 200 and r.json().get("total", 0) > 0, str(r.status_code))

        r = client.get("/portal/statistics")
        check("GET /portal/statistics", r.status_code == 200
              and r.json().get("inventory", {}).get("properties", 0) > 0, str(r.status_code))

        r = client.get("/portal/availability", params={"city": "Lahore"})
        check("GET /portal/availability", r.status_code == 200 and r.json().get("count", 0) > 0, str(r.status_code))

        r = client.get("/portal/market-trends", params={"city": "Lahore"})
        check("GET /portal/market-trends", r.status_code == 200
              and r.json().get("forecast", {}).get("base_cagr", 0) > 0, str(r.status_code))

        r = client.get("/gis/map", params={"lat": 31.4504, "lon": 74.2810, "include_poi": True})
        check("GET /gis/map (point + poi)", r.status_code == 200 and "leaflet" in r.text.lower(), str(r.status_code))

        # --- hierarchy / big-project / CRM / image / memory parity routes ---
        r = client.post("/cities", json={"name": "REST Test City", "latitude": 31.0, "longitude": 74.0})
        check("POST /cities", r.status_code == 201 and bool(r.json().get("id")), f"{r.status_code} {r.text[:120]}")

        r = client.post("/schemes", json={"name": "REST Test Society", "city_id": core.cities_db[0].id})
        check("POST /schemes", r.status_code == 201, f"{r.status_code} {r.text[:120]}")

        r = client.get("/blocks")
        check("GET /blocks", r.status_code == 200 and r.json().get("count", 0) > 0, str(r.status_code))

        r = client.post("/blocks", json={"name": "REST Block", "scheme_id": core.housing_schemes_db[0].id,
                                         "area_type": "block"})
        check("POST /blocks", r.status_code == 201, f"{r.status_code} {r.text[:120]}")

        r = client.get("/cities/" + core.cities_db[0].id)
        check("GET /cities/{id}", r.status_code == 200 and r.json().get("city", {}).get("name"), str(r.status_code))

        r = client.get("/cities/" + core.cities_db[0].id + "/coordinates")
        check("GET /cities/{id}/coordinates", r.status_code == 200, str(r.status_code))

        r = client.post("/bigprojects", json={"name": "REST Tower", "project_type": "tower",
                                              "city_id": core.cities_db[0].id})
        rest_project = r.json() if r.status_code == 201 else {}
        check("POST /bigprojects", r.status_code == 201 and bool(rest_project.get("id")), f"{r.status_code} {r.text[:120]}")

        if rest_project.get("id"):
            r = client.put(f"/bigprojects/{rest_project['id']}", json={"description": "REST updated"})
            check("PUT /bigprojects/{id}", r.status_code == 200, str(r.status_code))

            r = client.post(f"/bigprojects/{rest_project['id']}/amenities", json={"amenity": "Sky lounge"})
            check("POST /bigprojects/{id}/amenities", r.status_code == 201, f"{r.status_code} {r.text[:120]}")

            r = client.delete(f"/bigprojects/{rest_project['id']}")
            check("DELETE /bigprojects/{id}", r.status_code == 200, str(r.status_code))

        r = client.put("/properties/" + core.properties_db[0].id + "/coordinates",
                       json={"latitude": 31.45, "longitude": 74.28})
        check("PUT /properties/{id}/coordinates", r.status_code == 200, str(r.status_code))

        r = client.get("/distance", params={"lat1": 31.45, "lon1": 74.28, "lat2": 31.50, "lon2": 74.33})
        check("GET /distance", r.status_code == 200 and r.json().get("km", 0) > 0, str(r.status_code))

        r = client.get("/gis/destination", params={"latitude": 31.45, "longitude": 74.28, "bearing": 90,
                                                   "distance_m": 1000})
        check("GET /gis/destination", r.status_code == 200 and "latitude" in r.json(), str(r.status_code))

        r = client.post("/gis/boundaries", json={"name": "REST Boundary", "entity_type": "scheme",
                                                 "entity_id": scheme_id,
                                                 "coordinates": [[31.44, 74.27], [31.44, 74.29], [31.46, 74.29], [31.46, 74.27]]})
        check("POST /gis/boundaries", r.status_code in (200, 201), f"{r.status_code} {r.text[:120]}")

        r = client.post("/gis/zones", json={"name": "REST Zone", "entity_type": "scheme", "entity_id": scheme_id,
                                            "zone_type": "residential",
                                            "coordinates": [[31.44, 74.27], [31.44, 74.29], [31.46, 74.29], [31.46, 74.27]]})
        check("POST /gis/zones", r.status_code in (200, 201), f"{r.status_code} {r.text[:120]}")

        r = client.post("/images", json={"entity_type": "property", "entity_id": core.properties_db[0].id,
                                         "image_url": "http://example.com/rest.jpg"})
        check("POST /images", r.status_code == 201, f"{r.status_code} {r.text[:120]}")

        r = client.get(f"/images/property/{core.properties_db[0].id}")
        check("GET /images/{type}/{id}", r.status_code == 200, str(r.status_code))

        r = client.post(f"/images/property/{core.properties_db[0].id}/primary", json={"image_index": 0})
        check("POST /images/.../primary", r.status_code == 200, str(r.status_code))

        r = client.get("/memory/retrieve", params={"key": "no.such.key"})
        check("GET /memory/retrieve", r.status_code == 200, str(r.status_code))

        r = client.get("/crm/interactions")
        check("GET /crm/interactions", r.status_code == 200, str(r.status_code))

        r = client.post("/crm/interactions", json={"entity_type": "lead", "entity_id": mcp_lead_id,
                                                   "channel": "call", "summary": "REST logged call"})
        check("POST /crm/interactions", r.status_code == 201, f"{r.status_code} {r.text[:120]}")
        r = client.get("/crm/interactions")
        check("GET /crm/interactions lists the latest across the CRM", r.status_code == 200 and r.json().get("count", 0) >= 1, str(r.json())[:120])

        # --- CRM intelligence, channels and webhooks (rules mode: no AI key in tests)
        r = client.get("/crm/insights", params={"days": 30})
        ins = r.json() if r.status_code == 200 else {}
        check("GET /crm/insights", r.status_code == 200 and "kpis" in ins and "priority_leads" in ins and "agents" in ins, str(r.status_code))
        r = client.get("/crm/channels")
        check("GET /crm/channels", r.status_code == 200 and {"email", "sms", "whatsapp", "inbound"} <= set(r.json()), str(r.status_code))
        r = client.post(f"/crm/ai/lead-brief/{mcp_lead_id}")
        check("POST /crm/ai/lead-brief", r.status_code == 200 and r.json().get("next_best_action") and r.json().get("drafts", {}).get("whatsapp"), r.text[:160])
        r = client.post(f"/crm/ai/lead-brief/{mcp_lead_id}", params={"lang": "ur"})
        check("POST /crm/ai/lead-brief?lang=ur", r.status_code == 200 and "السلام" in r.json().get("drafts", {}).get("whatsapp", ""), r.text[:160])
        r = client.post("/crm/ai/lead-brief/no-such-lead")
        check("POST /crm/ai/lead-brief (404)", r.status_code == 404, str(r.status_code))
        r = client.post("/crm/ai/draft", json={"entity_id": mcp_lead_id, "channel": "email", "goal": "site_visit"})
        check("POST /crm/ai/draft", r.status_code == 200 and r.json().get("body") and r.json().get("subject"), r.text[:160])
        tasks_before = len(core.tasks_db)
        r = client.post("/crm/ai/note", json={"entity_id": mcp_lead_id, "text": "Budget 2.5 crore, wants a site visit tomorrow"})
        note = r.json() if r.status_code == 200 else {}
        check("POST /crm/ai/note (typed) -> analysis, interaction and task",
              r.status_code == 200 and note["analysis"].get("budget_pkr") == 25_000_000 and len(core.tasks_db) == tasks_before + 1, r.text[:200])
        r = client.post("/crm/ai/note", json={"audio_base64": "AAAA", "entity_id": mcp_lead_id})
        check("POST /crm/ai/note (voice without OpenAI -> 501)", r.status_code == 501, str(r.status_code))
        r = client.post("/crm/messages/send", json={"channel": "whatsapp", "body": "Test", "to": "0300 1234567", "entity_id": mcp_lead_id})
        check("POST /crm/messages/send (simulated, logged)", r.status_code == 200 and r.json().get("status") == "simulated" and r.json().get("interaction"), r.text[:160])
        r = client.post("/crm/messages/send", json={"channel": "email", "body": "Test", "to": "not-an-email"})
        check("POST /crm/messages/send (bad address -> 502)", r.status_code == 502, str(r.status_code))
        r = client.post("/crm/ai/ask", json={"question": "who should I call first?"})
        check("POST /crm/ai/ask", r.status_code == 200 and r.json().get("answer"), r.text[:160])
        r = client.post("/crm/webhooks/lead", params={"source": "facebook"}, json={
            "field_data": [{"name": "full_name", "values": ["Webhook Lead"]}, {"name": "phone_number", "values": ["0321-7654321"]}]})
        hook = r.json() if r.status_code == 200 else {}
        check("POST /crm/webhooks/lead (Facebook lead ad)", hook.get("created") is True and hook.get("agent_id"), r.text[:160])
        r = client.post("/crm/webhooks/lead", json={"name": "Webhook Lead", "phone": "+92 321 7654321"})
        check("POST /crm/webhooks/lead de-duplicates by phone", r.status_code == 200 and r.json().get("created") is False and r.json().get("lead_id") == hook.get("lead_id"), r.text[:160])
        r = client.post("/crm/webhooks/whatsapp", json={"entry": [{"changes": [{"value": {
            "contacts": [{"wa_id": "923459998887", "profile": {"name": "WA Lead"}}],
            "messages": [{"from": "923459998887", "type": "text", "text": {"body": "Is it available?"}}]}}]}]})
        check("POST /crm/webhooks/whatsapp", r.status_code == 200 and r.json().get("handled") == 1, r.text[:160])
        r = client.get("/crm/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "x", "hub.challenge": "1"})
        check("GET /crm/webhooks/whatsapp (no verify token -> 403)", r.status_code == 403, str(r.status_code))

        r = client.post("/crm/agents", json={"name": "REST Agent", "email": "rest.agent@example.com",
                                             "region": "Lahore"})
        check("POST /crm/agents", r.status_code == 201, f"{r.status_code} {r.text[:120]}")

        r = client.post("/crm/customers", json={"name": "REST Customer", "email": "rest.cust@example.com",
                                                "type": "buyer"})
        check("POST /crm/customers", r.status_code == 201, f"{r.status_code} {r.text[:120]}")

        r = client.put(f"/crm/leads/{mcp_lead_id}", json={"status": "contacted"})
        check("PUT /crm/leads/{id}", r.status_code == 200, str(r.status_code))

        r = client.get("/auth/otps")
        check("GET /auth/otps (shared tool)", r.status_code == 200 and "otps" in r.json(), str(r.status_code))

        # --- portal content over REST ---
        r = client.get("/content/overview")
        check("GET /content/overview", r.status_code == 200
              and r.json().get("counts", {}).get("pages", 0) > 0, str(r.status_code))

        r = client.get("/content/pages")
        check("GET /content/pages", r.status_code == 200 and r.json().get("count", 0) > 0, str(r.status_code))

        r = client.get("/content/pages/about")
        check("GET /content/pages/about", r.status_code == 200 and r.json().get("key") == "about", str(r.status_code))

        r = client.post("/content/pages", json={"key": "rest-page", "title": "REST Page",
                                                "category": "help", "body": ["REST body"]})
        check("POST /content/pages", r.status_code == 201 and r.json().get("key") == "rest-page", str(r.status_code))

        r = client.put("/content/pages/rest-page", json={"summary": "REST updated"})
        check("PUT /content/pages/{key}", r.status_code == 200 and r.json().get("summary") == "REST updated",
              str(r.status_code))

        r = client.delete("/content/pages/rest-page")
        check("DELETE /content/pages/{key}", r.status_code == 200, str(r.status_code))

        r = client.get("/content/history")
        check("GET /content/history", r.status_code == 200 and r.json().get("count", 0) > 0, str(r.status_code))

        r = client.post("/content/history", json={"year": 2027, "title": "REST milestone",
                                                  "description": "Added over REST", "kind": "milestone"})
        check("POST /content/history", r.status_code == 201, f"{r.status_code} {r.text[:100]}")

        r = client.get("/content/contacts")
        check("GET /content/contacts", r.status_code == 200 and r.json().get("count", 0) > 0, str(r.status_code))

        r = client.post("/content/contacts", json={"channel_type": "email", "label": "REST desk",
                                                   "value": "rest@portal.pk"})
        check("POST /content/contacts", r.status_code == 201, f"{r.status_code} {r.text[:100]}")

        r = client.get("/content/stories")
        check("GET /content/stories", r.status_code == 200 and r.json().get("count", 0) > 0, str(r.status_code))

        r = client.post("/content/stories", json={"title": "REST Story", "story_type": "testimonial",
                                                  "quote": "Great portal"})
        check("POST /content/stories", r.status_code == 201, f"{r.status_code} {r.text[:100]}")

        r = client.get("/content/navigation")
        check("GET /content/navigation", r.status_code == 200 and len(r.json().get("items", [])) > 0, str(r.status_code))

        r = client.get("/content/site", params={"lang": "ur"})
        check("GET /content/site", r.status_code == 200 and len(r.json().get("layout", [])) > 0, str(r.status_code))

        r = client.get("/portal/home")
        check("GET /portal/home", r.status_code == 200 and "ad-section" in r.text, str(r.status_code))

        r = client.get("/portal/home.html", params={"lang": "ur", "theme": "dark"})
        check("GET /portal/home.html (ur/dark)", r.status_code == 200 and 'dir="rtl"' in r.text, str(r.status_code))

        # --- advertising over REST ---
        r = client.get("/ads/categories")
        check("GET /ads/categories", r.status_code == 200 and r.json().get("count", 0) >= 10, str(r.status_code))

        r = client.get("/ads/slots")
        check("GET /ads/slots", r.status_code == 200 and r.json().get("count", 0) >= 5, str(r.status_code))

        r = client.get("/ads")
        check("GET /ads", r.status_code == 200 and r.json().get("count", 0) > 0, str(r.status_code))

        r = client.get("/ads/active", params={"slot": "hero"})
        check("GET /ads/active", r.status_code == 200 and r.json().get("count", 0) > 0, str(r.status_code))

        r = client.get("/ads/performance")
        check("GET /ads/performance", r.status_code == 200 and r.json().get("totals", {}).get("ads", 0) > 0,
              str(r.status_code))

        r = client.get("/ads/section", params={"slot": "infeed", "category": "materials"})
        check("GET /ads/section", r.status_code == 200 and r.json().get("kind") == "ads", str(r.status_code))

        r = client.post("/ads", json={"title": "REST Ad", "headline": "REST headline",
                                      "category": "solar_energy", "slot": "sidebar",
                                      "advertiser": "REST Solar", "budget": 100000})
        rest_ad_id = r.json().get("id") if r.status_code == 201 else None
        check("POST /ads", r.status_code == 201 and bool(rest_ad_id), f"{r.status_code} {r.text[:100]}")

        if rest_ad_id:
            r = client.get(f"/ads/{rest_ad_id}")
            check("GET /ads/{ad_id}", r.status_code == 200 and r.json().get("id") == rest_ad_id, str(r.status_code))

            r = client.post(f"/ads/{rest_ad_id}/track", params={"event": "impression", "count": 10})
            check("POST /ads/{ad_id}/track", r.status_code == 200 and r.json().get("impressions", 0) >= 10,
                  str(r.status_code))

            r = client.put(f"/ads/{rest_ad_id}", json={"headline": "REST updated headline"})
            check("PUT /ads/{ad_id}", r.status_code == 200
                  and r.json().get("headline") == "REST updated headline", str(r.status_code))

            r = client.delete(f"/ads/{rest_ad_id}")
            check("DELETE /ads/{ad_id}", r.status_code == 200, str(r.status_code))

        # --- ads in the apps: network config, billing, deduplicated tracking ---
        import ads_network
        ads_network.reset()
        r = client.get("/ads/config")
        cfg = r.json() if r.status_code == 200 else {}
        check("GET /ads/config", cfg.get("direct") is True and "advertise" in cfg
              and (cfg.get("admob") is None or "banner" in cfg["admob"]), str(cfg)[:200])
        r = client.get("/ads.txt")
        check("GET /ads.txt (no AdSense -> 404)", r.status_code == (200 if ads_network.ADSENSE_CLIENT else 404), str(r.status_code))
        r = client.post("/ads", json={"title": "CPC Ad", "headline": "Pay per click", "category": "solar_energy",
                                      "slot": "infeed", "pricing": "cpc", "rate": 50, "budget": 100})
        cpc_id = r.json().get("id") if r.status_code == 201 else None
        check("POST /ads (cpc pricing)", bool(cpc_id) and r.json().get("pricing") == "cpc", r.text[:120])
        r = client.post("/ads", json={"title": "Bad", "headline": "Bad", "pricing": "per-hour"})
        check("POST /ads (unknown pricing rejected)", "error" in r.json(), r.text[:120])
        if cpc_id:
            r1 = client.post(f"/ads/{cpc_id}/event", json={"event": "click"}).json()
            r2 = client.post(f"/ads/{cpc_id}/event", json={"event": "click"}).json()
            check("POST /ads/{id}/event (click billed once per viewer)",
                  r1.get("counted") is True and r1.get("spend") == 50 and r2.get("counted") is False, f"{r1} {r2}")
            r = client.post(f"/ads/{cpc_id}/event", json={"event": "impression"}).json()
            check("POST /ads/{id}/event (impression)", r.get("counted") is True and r.get("impressions") == 1, str(r))
            ads_network.reset()
            r = client.post(f"/ads/{cpc_id}/event", json={"event": "click"}).json()
            check("ads: budget spent -> paused", r.get("spend") == 100 and r.get("status") == "paused", str(r))
            client.delete(f"/ads/{cpc_id}")
        r = client.post("/ads/does-not-exist/event", json={"event": "click"})
        check("POST /ads/{id}/event (unknown -> 404)", r.status_code == 404, str(r.status_code))
        r = client.post("/ads/does-not-exist/event", json={"event": "like"})
        check("POST /ads/{id}/event (bad event -> 422)", r.status_code == 422, str(r.status_code))
        r = client.get("/ads", params={"limit": 200})
        seeded = [a for a in r.json().get("advertisements", []) if a.get("sample")]
        names = " ".join(f"{a['title']} {a['advertiser']} {a.get('cta_url') or ''}" for a in seeded)
        check("seed ads are fictional samples linking to example.com",
              len(seeded) >= 20 and not any(b in names for b in ("HBL", "Habib", "State Bank", "TPL", ".pk/"))
              and all((a.get("cta_url") or "https://example.com").startswith("https://example.com") for a in seeded),
              names[:200])
        ads_network.reset()

        r = client.get("/ads/preview", params={"slot": "hero"})
        check("GET /ads/preview", r.status_code == 200 and "ad-card" in r.text, str(r.status_code))

        r = client.get("/ads/report")
        check("GET /ads/report", r.status_code == 200 and "ad-section" in r.text, str(r.status_code))

        # --- users & roles (RBAC) over REST ---
        r = client.get("/roles")
        check("GET /roles", r.status_code == 200 and r.json().get("count", 0) >= 10, str(r.status_code))

        r = client.get("/roles/permissions")
        check("GET /roles/permissions", r.status_code == 200 and r.json().get("count", 0) > 0, str(r.status_code))

        r = client.get("/roles/summary")
        check("GET /roles/summary", r.status_code == 200 and r.json().get("roles", 0) > 0, str(r.status_code))

        r = client.get("/roles/agent")
        check("GET /roles/{name}", r.status_code == 200 and r.json().get("name") == "agent", str(r.status_code))

        r = client.get("/roles/agent/users")
        check("GET /roles/{name}/users", r.status_code == 200 and r.json().get("count", 0) > 0, str(r.status_code))

        r = client.post("/roles", json={"name": "rest_role", "label": "REST Role",
                                        "portal_area": "staff", "permissions": ["content.view"]})
        check("POST /roles", r.status_code == 201 and r.json().get("name") == "rest_role",
              f"{r.status_code} {r.text[:100]}")

        r = client.put("/roles/rest_role", json={"label": "REST Role Renamed"})
        check("PUT /roles/{name}", r.status_code == 200
              and r.json().get("label") == "REST Role Renamed", str(r.status_code))

        r = client.delete("/roles/rest_role")
        check("DELETE /roles/{name}", r.status_code == 200 and r.json().get("deleted") == "rest_role", str(r.status_code))

        rest_user_id = core.auth.users_db[0].id if core.auth.users_db else None
        if rest_user_id:
            r = client.get(f"/users/{rest_user_id}/roles")
            check("GET /users/{id}/roles", r.status_code == 200 and len(r.json().get("roles", [])) > 0,
                  str(r.status_code))

            r = client.get(f"/users/{rest_user_id}/permissions")
            check("GET /users/{id}/permissions", r.status_code == 200
                  and len(r.json().get("permissions", [])) > 0, str(r.status_code))

            r = client.post(f"/users/{rest_user_id}/permissions", json={"permission": "content.view"})
            check("POST /users/{id}/permissions", r.status_code == 200, f"{r.status_code} {r.text[:100]}")

            r = client.get(f"/users/{rest_user_id}/permissions/check", params={"permission": "content.view"})
            check("GET /users/{id}/permissions/check", r.status_code == 200
                  and r.json().get("allowed") is True, str(r.json()))

            r = client.delete(f"/users/{rest_user_id}/permissions/content.view")
            check("DELETE /users/{id}/permissions/{permission}", r.status_code == 200, str(r.status_code))

            r = client.post(f"/users/{rest_user_id}/roles", json={"role": "moderator"})
            check("POST /users/{id}/roles", r.status_code in (200, 201), f"{r.status_code} {r.text[:100]}")

            r = client.delete(f"/users/{rest_user_id}/roles/moderator")
            check("DELETE /users/{id}/roles/{role}", r.status_code == 200, str(r.status_code))

        # --- routing over REST (on foot / by car) ---
        r = client.get("/gis/travel-modes")
        check("GET /gis/travel-modes", r.status_code == 200 and len(r.json().get("modes", [])) >= 3, str(r.status_code))

        r = client.get("/gis/road-classes")
        check("GET /gis/road-classes", r.status_code == 200 and r.json().get("count", 0) > 0, str(r.status_code))

        route_params = {"origin_latitude": 31.4504, "origin_longitude": 74.2810,
                        "destination_latitude": 31.4690, "destination_longitude": 74.4120}
        r = client.get("/gis/route", params={**route_params, "mode": "drive", "alternatives": 2})
        check("GET /gis/route (drive)", r.status_code == 200
              and r.json().get("best", {}).get("distance_m", 0) > 0, str(r.status_code))

        r = client.get("/gis/route/compare", params=route_params)
        check("GET /gis/route/compare", r.status_code == 200
              and set(r.json().get("modes", {})) >= {"walk", "drive"}, str(r.status_code))

        r = client.post("/gis/route/matrix", json={"poi_ids": ["Smart City Public School", "Downtown Shopping Mall"],
                                                   "mode": "drive"})
        check("POST /gis/route/matrix", r.status_code == 200 and len(r.json().get("matrix", [])) == 2, str(r.status_code))

        r = client.post("/gis/road-networks", json={"name": "rest-way-net", "ways": [
            {"coordinates": [[31.45, 74.27], [31.46, 74.28], [31.47, 74.29]], "road_class": "local"}]})
        check("POST /gis/road-networks", r.status_code == 201 and r.json().get("nodes") == 3,
              f"{r.status_code} {r.text[:100]}")

        r = client.get("/gis/road-networks")
        check("GET /gis/road-networks", r.status_code == 200 and r.json().get("count", 0) > 0, str(r.status_code))

        r = client.get("/gis/route/map", params={**route_params, "mode": "drive"})
        check("GET /gis/route/map", r.status_code == 200 and "leaflet" in r.text.lower(), str(r.status_code))

        r = client.get("/poi/route", params={"origin_poi": "Smart City Public School",
                                             "destination_poi": "Downtown Shopping Mall", "mode": "walk"})
        check("GET /poi/route (walk)", r.status_code == 200
              and r.json().get("mode") == "walk", str(r.status_code))

        # --- construction wing over REST ---
        r = client.get("/construction/overview")
        check("GET /construction/overview", r.status_code == 200 and r.json()["counts"]["systems"] >= 10,
              str(r.status_code))

        r = client.get("/construction/techniques")
        check("GET /construction/techniques", r.status_code == 200 and r.json()["count"] >= 10, str(r.status_code))

        r = client.get("/construction/techniques/rcc_frame")
        check("GET /construction/techniques/{key}", r.status_code == 200 and r.json().get("key") == "rcc_frame",
              str(r.status_code))

        r = client.get("/construction/materials", params={"category": "steel"})
        check("GET /construction/materials", r.status_code == 200 and r.json()["count"] >= 2, str(r.status_code))

        r = client.get("/construction/materials/cement_opc")
        check("GET /construction/materials/{key}", r.status_code == 200 and r.json().get("key") == "cement_opc",
              str(r.status_code))

        r = client.get("/construction/element-rates")
        check("GET /construction/element-rates", r.status_code == 200 and r.json()["count"] >= 10, str(r.status_code))

        r = client.get("/construction/rate-analysis", params={"element": "rcc"})
        check("GET /construction/rate-analysis", r.status_code == 200 and r.json()["total_rate"] > 0, str(r.status_code))

        r = client.post("/construction/estimate", json={"covered_area": 2000, "floors": 2,
                                                        "quality_tier": "standard"})
        check("POST /construction/estimate", r.status_code == 200 and r.json()["cost"]["total"] > 0, str(r.status_code))

        r = client.get("/construction/timeline", params={"covered_area": 2000})
        check("GET /construction/timeline", r.status_code == 200 and r.json()["total_days"] > 0, str(r.status_code))

        r = client.get("/construction/takeoff", params={"covered_area": 2000})
        check("GET /construction/takeoff", r.status_code == 200 and len(r.json()["lines"]) >= 8, str(r.status_code))

        r = client.get("/construction/compare", params={"covered_area": 2000})
        check("GET /construction/compare", r.status_code == 200 and r.json()["count"] >= 3, str(r.status_code))

        r = client.get("/construction/impact", params={"covered_area": 2000})
        check("GET /construction/impact", r.status_code == 200 and r.json()["value_uplift"] > 0, str(r.status_code))

        r = client.get("/construction/advisory", params={"plot_area": 2722.5, "soil": "clay"})
        check("GET /construction/advisory", r.status_code == 200 and bool(r.json()["recommended_system"]),
              str(r.status_code))

        r = client.get("/construction/guidelines")
        check("GET /construction/guidelines", r.status_code == 200 and r.json()["count"] >= 8, str(r.status_code))

        r = client.get("/construction/approvals", params={"project_type": "apartment"})
        check("GET /construction/approvals", r.status_code == 200 and r.json()["step_count"] >= 5, str(r.status_code))

        r = client.get("/construction/qa", params={"stage": "structure"})
        check("GET /construction/qa", r.status_code == 200 and r.json().get("stage") == "structure", str(r.status_code))

        r = client.get("/construction/hse")
        check("GET /construction/hse", r.status_code == 200 and r.json()["count"] >= 5, str(r.status_code))

        r = client.get("/construction/trades")
        check("GET /construction/trades", r.status_code == 200 and r.json()["count"] >= 8, str(r.status_code))

        r = client.post("/construction/estimates", json={"title": "REST est", "covered_area": 1800})
        check("POST /construction/estimates", r.status_code == 201 and r.json()["saved"]["total_cost"] > 0,
              str(r.status_code))
        rest_est_id = r.json()["saved"]["id"]

        r = client.get("/construction/estimates")
        check("GET /construction/estimates", r.status_code == 200 and r.json()["count"] >= 1, str(r.status_code))

        r = client.get(f"/construction/estimates/{rest_est_id}")
        check("GET /construction/estimates/{estimate_id}", r.status_code == 200, str(r.status_code))

        r = client.get("/construction/portal")
        check("GET /construction/portal", r.status_code == 200 and "Construction wing" in r.text, str(r.status_code))

        r = client.get("/construction/portal.html", params={"lang": "ur"})
        check("GET /construction/portal.html (ur)", r.status_code == 200 and "تعمیرات" in r.text, str(r.status_code))

        r = client.post("/construction/report", json={"covered_area": 2000})
        check("POST /construction/report", r.status_code == 200 and "Element build-up" in r.text, str(r.status_code))

        # --- maintenance wing over REST ---
        r = client.get("/maintenance/overview")
        check("GET /maintenance/overview", r.status_code == 200 and r.json()["counts"]["components"] >= 10,
              str(r.status_code))

        r = client.get("/maintenance/components")
        check("GET /maintenance/components", r.status_code == 200 and r.json()["count"] >= 10, str(r.status_code))

        r = client.get("/maintenance/components/hvac")
        check("GET /maintenance/components/{key}", r.status_code == 200 and r.json().get("key") == "hvac",
              str(r.status_code))

        r = client.get("/maintenance/services", params={"emergency": True})
        check("GET /maintenance/services", r.status_code == 200 and r.json()["count"] >= 3, str(r.status_code))

        r = client.get("/maintenance/services/ac_service")
        check("GET /maintenance/services/{key}", r.status_code == 200 and r.json().get("key") == "ac_service",
              str(r.status_code))

        r = client.get("/maintenance/defects", params={"severity": "high"})
        check("GET /maintenance/defects", r.status_code == 200 and r.json()["count"] >= 3, str(r.status_code))

        r = client.get("/maintenance/defects/roof_seepage")
        check("GET /maintenance/defects/{key}", r.status_code == 200 and r.json().get("key") == "roof_seepage",
              str(r.status_code))

        r = client.get("/maintenance/estimate", params={"covered_area": 2000, "age_years": 8})
        check("GET /maintenance/estimate", r.status_code == 200 and r.json()["annual"]["total"] > 0, str(r.status_code))

        r = client.get("/maintenance/schedule", params={"horizon_months": 12})
        check("GET /maintenance/schedule", r.status_code == 200 and r.json()["task_count"] > 0, str(r.status_code))

        r = client.get("/maintenance/lifecycle", params={"covered_area": 4000, "property_type": "apartment"})
        check("GET /maintenance/lifecycle", r.status_code == 200 and r.json()["total_replacement_cost"] > 0,
              str(r.status_code))

        r = client.get("/maintenance/reserve", params={"covered_area": 2000})
        check("GET /maintenance/reserve", r.status_code == 200 and r.json()["annual_reserve"] > 0, str(r.status_code))

        r = client.get("/maintenance/condition", params={"age_years": 5})
        check("GET /maintenance/condition", r.status_code == 200 and r.json()["score"] > 0, str(r.status_code))

        r = client.get("/maintenance/repair-estimate", params={"defect": "roof_seepage", "quantity": 300})
        check("GET /maintenance/repair-estimate", r.status_code == 200 and r.json()["cost_mid"] > 0, str(r.status_code))

        r = client.get("/maintenance/repair-or-replace", params={"component": "roof_waterproofing", "age_years": 9})
        check("GET /maintenance/repair-or-replace", r.status_code == 200 and r.json()["decision"] in ("repair", "replace"),
              str(r.status_code))

        r = client.get("/maintenance/impact", params={"market_value": 12000000, "monthly_rent": 90000})
        check("GET /maintenance/impact", r.status_code == 200 and r.json()["value_uplift"] > 0, str(r.status_code))

        r = client.get("/maintenance/guidelines")
        check("GET /maintenance/guidelines", r.status_code == 200 and r.json()["count"] >= 5, str(r.status_code))

        r = client.get("/maintenance/warranty", params={"component": "roof_waterproofing"})
        check("GET /maintenance/warranty", r.status_code == 200 and r.json().get("years", 0) > 0, str(r.status_code))

        r = client.get("/maintenance/inspection", params={"area": "mep"})
        check("GET /maintenance/inspection", r.status_code == 200 and len(r.json()["checks"]) >= 3, str(r.status_code))

        r = client.post("/maintenance/plans", json={"title": "REST AMC", "covered_area": 2500})
        check("POST /maintenance/plans", r.status_code == 201 and r.json()["saved"]["annual_cost"] > 0,
              str(r.status_code))
        rest_plan_id = r.json()["saved"]["id"]

        r = client.get("/maintenance/plans")
        check("GET /maintenance/plans", r.status_code == 200 and r.json()["count"] >= 1, str(r.status_code))

        r = client.get(f"/maintenance/plans/{rest_plan_id}")
        check("GET /maintenance/plans/{plan_id}", r.status_code == 200, str(r.status_code))

        r = client.post("/maintenance/work-orders", json={"title": "REST WO", "component": "electrical",
                                                          "priority": "urgent", "estimated_cost": 5000})
        check("POST /maintenance/work-orders", r.status_code == 201 and r.json()["status"] == "open",
              str(r.status_code))
        rest_wo_id = r.json()["id"]

        r = client.get("/maintenance/work-orders", params={"priority": "urgent"})
        check("GET /maintenance/work-orders", r.status_code == 200 and r.json()["count"] >= 1, str(r.status_code))

        r = client.get(f"/maintenance/work-orders/{rest_wo_id}")
        check("GET /maintenance/work-orders/{wo_id}", r.status_code == 200 and r.json()["id"] == rest_wo_id,
              str(r.status_code))

        r = client.put(f"/maintenance/work-orders/{rest_wo_id}", json={"status": "done"})
        check("PUT /maintenance/work-orders/{wo_id}", r.status_code == 200 and r.json()["status"] == "done",
              str(r.status_code))

        r = client.get("/maintenance/portal")
        check("GET /maintenance/portal", r.status_code == 200 and "Maintenance wing" in r.text, str(r.status_code))

        r = client.get("/maintenance/portal.html", params={"lang": "ur"})
        check("GET /maintenance/portal.html (ur)", r.status_code == 200 and "دیکھ بھال" in r.text, str(r.status_code))

        r = client.post("/maintenance/report", json={"covered_area": 2000, "property_type": "apartment"})
        check("POST /maintenance/report", r.status_code == 200 and "Maintenance summary" in r.text, str(r.status_code))

        # --- MCP endpoint reachable (no session needed in stateless mode). A
        #     JSON-RPC error envelope still proves the route is mounted. ---
        r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                        headers={"Accept": "application/json, text/event-stream"})
        check("POST /mcp tools/list (no session)", r.status_code in (200, 202, 400, 406, 421),
              f"status={r.status_code}")

        # --- agentic products (REST), reusing this already-entered client ---
        run_products_rest_checks(client)

        # --- tools & utilities (REST), reusing this already-entered client ---
        run_tools_rest_checks(client)

        # --- PMO / project management (REST), reusing this already-entered client ---
        run_pmo_rest_checks(client)

        # --- team messaging & notifications (REST), reusing this already-entered client ---
        run_messaging_rest_checks(client)


# ============================================================
# 1c) Agentic products (MCP): agents, transactions, intelligence,
#     leasing, marketing, commercialization
# ============================================================


async def run_products_checks() -> None:
    print("\n=== Agentic products (MCP) ===")
    async with Client(core.mcp) as client:
        # ---------------- agents / Agentic OS ----------------
        r = json.loads(text_of(await client.call_tool("agents_overview", {})))
        check("tool: agents_overview", r["counts"]["agents"] >= 20 and r["counts"]["products"] == 8,
              str(r["counts"]))

        r = json.loads(text_of(await client.call_tool("agents_catalog", {"category": "broker"})))
        check("tool: agents_catalog (broker)", r["count"] >= 1, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("agent_get", {"key": "conversational_buyer_agent"})))
        check("tool: agent_get", r.get("key") == "conversational_buyer_agent", str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("agent_products", {})))
        check("tool: agent_products", r["count"] == 8, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("agent_plan", {
            "agent_key": "conversational_buyer_agent", "objective": "find a 3-bed house"})))
        check("tool: agent_plan", len(r.get("steps", [])) >= 3, str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("agent_run", {
            "agent_key": "conversational_buyer_agent", "objective": "find a house",
            "text": "budget 3 crore, 3 bed house in Lahore, 35 min commute"})))
        STATE["run_id"] = r.get("id")
        check("tool: agent_run", bool(r.get("id")) and r.get("status") in ("completed", "awaiting_approval"),
              str(r.get("status")))

        r = json.loads(text_of(await client.call_tool("agent_runs", {})))
        check("tool: agent_runs", r["count"] >= 1, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("agent_run_get", {"run_id": STATE["run_id"]})))
        check("tool: agent_run_get", r.get("id") == STATE["run_id"], str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("agent_run", {
            "agent_key": "transaction_agent", "objective": "review a deal", "approve": False})))
        paused = r.get("id")
        r2 = json.loads(text_of(await client.call_tool("agent_approve", {"run_id": paused})))
        check("tool: agent_approve", r.get("status") == "awaiting_approval" and r2.get("status") is not None,
              str((r.get("status"), r2.get("status"))))

        r = json.loads(text_of(await client.call_tool("agent_smart_actions", {"limit": 5})))
        check("tool: agent_smart_actions", r["count"] >= 1 and "by_band" in r, str(r.get("count")))

        r = json.loads(text_of(await client.call_tool("agent_move_likelihood",
                                                      {"lead_id": core.leads_db[0].id})))
        check("tool: agent_move_likelihood", 0 <= r["move_likelihood"]["score"] <= 100,
              str(r["move_likelihood"]["band"]))

        r = json.loads(text_of(await client.call_tool("agent_seller_intent",
                                                      {"equity_pct": 60, "holding_years": 9, "market_heat": 0.8})))
        check("tool: agent_seller_intent", r.get("score", -1) >= 0, str(r.get("band")))

        r = json.loads(text_of(await client.call_tool("agent_orchestrate", {
            "objective": "close a deal",
            "agents_csv": "conversational_buyer_agent,seller_pricing_agent,transaction_agent"})))
        check("tool: agent_orchestrate", r.get("count", 0) == 3, str(r.get("count")))

        # ---------------- transactions ----------------
        r = json.loads(text_of(await client.call_tool("transaction_stages", {})))
        check("tool: transaction_stages", len(r["stages"]) >= 5, str(len(r["stages"])))

        r = json.loads(text_of(await client.call_tool("transaction_create", {
            "transaction_type": "sale", "price": 30_000_000, "property_title": "MCP Test House",
            "buyer_name": "A", "seller_name": "B"})))
        tx_id = r["transaction"]["id"]
        STATE["tx_id"] = tx_id
        check("tool: transaction_create", bool(tx_id) and r["transaction"]["stage"], str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("transactions_list", {"status": "open"})))
        check("tool: transactions_list", r["count"] >= 1, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("transaction_get", {"tx_id": tx_id})))
        check("tool: transaction_get", r.get("id") == tx_id and "offers" in r, str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("transaction_update",
                                                      {"tx_id": tx_id, "stage": "under_contract"})))
        check("tool: transaction_update", r.get("transaction", {}).get("stage") == "under_contract",
              str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("transaction_milestone_add", {
            "tx_id": tx_id, "key": "custom", "name": "Custom", "due_date": "2027-01-01"})))
        check("tool: transaction_milestone_add", "error" not in r, str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("transaction_milestone_complete",
                                                      {"tx_id": tx_id, "key": "custom"})))
        check("tool: transaction_milestone_complete", "error" not in r, str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("transaction_extract_terms", {
            "text": "Sale price PKR 30,000,000. Commission 2%. Possession on 2026-12-01. Mr A."})))
        check("tool: transaction_extract_terms", r.get("term_count", 0) >= 2, str(r.get("term_count")))

        r = json.loads(text_of(await client.call_tool("transaction_offer_add", {
            "tx_id": tx_id, "price": 29_000_000, "buyer_name": "A"})))
        offer_id = r["offer"]["id"]
        check("tool: transaction_offer_add", bool(offer_id), str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("transaction_offer_respond",
                                                      {"offer_id": offer_id, "action": "accept"})))
        check("tool: transaction_offer_respond", "error" not in r, str(r.get("error")))

        json.loads(text_of(await client.call_tool("transaction_signature_add",
                                                  {"tx_id": tx_id, "signer": "A", "role": "buyer", "signed": True})))
        r = json.loads(text_of(await client.call_tool("transaction_signature_add",
                                                      {"tx_id": tx_id, "signer": "B", "role": "seller", "signed": True})))
        check("tool: transaction_signature_add", r.get("signature", r).get("role") in ("seller", None) or "error" not in r,
              str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("transaction_signatures", {"tx_id": tx_id})))
        check("tool: transaction_signatures", r.get("complete") is True, str(r.get("complete")))

        r = json.loads(text_of(await client.call_tool("transaction_progress", {"tx_id": tx_id})))
        check("tool: transaction_progress", "progress_pct" in r and r["rag"] in ("red", "amber", "green"),
              str(r.get("rag")))

        r = json.loads(text_of(await client.call_tool("transaction_deadlines", {"horizon_days": 120})))
        check("tool: transaction_deadlines", r.get("count", 0) >= 1, str(r.get("count")))

        r = json.loads(text_of(await client.call_tool("transaction_close", {"tx_id": tx_id})))
        check("tool: transaction_close", r.get("balanced") is True and r["commission"]["gross"] > 0,
              str(r.get("commission")))
        check("tool: transaction_close posts a ledger entry",
              bool(r.get("journal_entry", {}).get("id")), str(r.get("journal_entry")))

        html = text_of(await client.call_tool("transaction_report", {"tx_id": tx_id}))
        check("tool: transaction_report", "Transaction summary" in html, str(len(html)))

        # ---------------- intelligence: buyer / seller / investor ----------------
        r = json.loads(text_of(await client.call_tool("buyer_parse_requirement", {
            "text": "3 bed house in Lahore, budget 3 crore, 35 minutes commute, good schools"})))
        check("tool: buyer_parse_requirement", r.get("bedrooms") == 3 and r.get("city") == "Lahore",
              str((r.get("bedrooms"), r.get("city"))))

        r = json.loads(text_of(await client.call_tool("buyer_recommend", {
            "text": "house in Lahore, budget 5 crore, good schools"})))
        check("tool: buyer_recommend", r.get("returned", 0) >= 1 and len(r.get("shortlist", [])) >= 1,
              str(r.get("returned")))

        r = json.loads(text_of(await client.call_tool("buyer_anomaly_scan", {})))
        check("tool: buyer_anomaly_scan", r.get("scanned", 0) >= 1, str(r.get("scanned")))

        r = json.loads(text_of(await client.call_tool("buyer_affordability", {
            "price": 28_000_000, "monthly_income": 400_000})))
        check("tool: buyer_affordability", "verdict" in r and r["monthly_payment"] > 0, str(r.get("verdict")))

        html = text_of(await client.call_tool("buyer_report", {"text": "3 bed house Lahore"}))
        check("tool: buyer_report", "Ranked shortlist" in html, str(len(html)))

        pid = core.properties_db[0].id
        r = json.loads(text_of(await client.call_tool("seller_cma", {"property_id": pid})))
        check("tool: seller_cma", r.get("price_range", {}).get("target", 0) > 0 and r.get("confidence", 0) > 0,
              str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("seller_net_proceeds", {
            "price": 30_000_000, "mortgage_payoff": 5_000_000})))
        check("tool: seller_net_proceeds", r.get("net_proceeds", 0) > 0, str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("seller_marketing_assets", {"property_id": pid})))
        check("tool: seller_marketing_assets", bool(r.get("headline")) and bool(r.get("description")),
              str(list(r)[:4]))

        html = text_of(await client.call_tool("seller_report", {"property_id": pid}))
        check("tool: seller_report", "Recommended pricing" in html, str(len(html)))

        r = json.loads(text_of(await client.call_tool("investment_underwrite", {
            "purchase_price": 20_000_000, "monthly_rent": 150_000})))
        check("tool: investment_underwrite", r["returns"]["cap_rate"] > 0 and "dscr" in r["debt"],
              str(r.get("grade")))

        r = json.loads(text_of(await client.call_tool("investment_screen", {"min_cap_rate": 0.02})))
        check("tool: investment_screen", r["considered"] >= 1 and r["passed"] >= 1, str(r.get("passed")))

        r = json.loads(text_of(await client.call_tool("investment_portfolio_alerts", {
            "interest_rate": 0.14, "market_heat": 0.8})))
        check("tool: investment_portfolio_alerts", r.get("count", 0) >= 1, str(r.get("count")))

        html = text_of(await client.call_tool("investment_report", {}))
        check("tool: investment_report", "Top risk-adjusted picks" in html, str(len(html)))

        # ---------------- leasing ----------------
        r = json.loads(text_of(await client.call_tool("leasing_units", {})))
        check("tool: leasing_units", r["count"] >= 1, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("leasing_unit_create", {
            "title": "MCP unit", "rent": 70_000, "monthly_holding_cost": 50_000})))
        unit_id = r["unit"]["id"]
        STATE["unit_id"] = unit_id
        check("tool: leasing_unit_create", bool(unit_id) and r["unit"]["floor_rent"] > 50_000,
              str(r["unit"].get("floor_rent")))

        r = json.loads(text_of(await client.call_tool("leasing_unit", {"unit_id": unit_id})))
        check("tool: leasing_unit", r.get("id") == unit_id, str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("leasing_rent_floor", {"monthly_holding_cost": 70_000})))
        check("tool: leasing_rent_floor", r["rent_floor"] > 70_000, str(r["rent_floor"]))

        r = json.loads(text_of(await client.call_tool("leasing_inquiry", {
            "message": "Is it still available and what is the rent?", "unit_id": unit_id})))
        check("tool: leasing_inquiry", r.get("intent") == "availability" and r.get("auto_handled") is True,
              str(r.get("intent")))

        r = json.loads(text_of(await client.call_tool("leasing_inquiries", {})))
        check("tool: leasing_inquiries", r["count"] >= 1, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("leasing_screen_application", {
            "applicant": "MCP applicant", "monthly_income": 300_000, "unit_id": unit_id})))
        check("tool: leasing_screen_application", r.get("decision") in ("approve", "conditional", "decline"),
              str(r.get("decision")))

        r = json.loads(text_of(await client.call_tool("leasing_renewals", {})))
        check("tool: leasing_renewals", r["count"] >= 1, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("leasing_collection", {})))
        check("tool: leasing_collection", "leases" in r and "total_outstanding" in r, str(list(r)))

        r = json.loads(text_of(await client.call_tool("leasing_funnel", {})))
        check("tool: leasing_funnel", r.get("inquiries", 0) >= 1, str(r.get("inquiries")))

        html = text_of(await client.call_tool("leasing_portal", {"lang": "en"}))
        check("tool: leasing_portal", "Autonomous Leasing wing" in html and "lc-out" in html, str(len(html)))

        # ---------------- marketing ----------------
        r = json.loads(text_of(await client.call_tool("marketing_channels", {})))
        check("tool: marketing_channels", len(r.get("channels", {})) >= 5, str(len(r.get("channels", {}))))

        r = json.loads(text_of(await client.call_tool("marketing_routes", {})))
        check("tool: marketing_routes", r["count"] >= 1, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("marketing_route_add", {
            "name": "MCP rule", "match": {"city": "Lahore"}, "queue": "test"})))
        check("tool: marketing_route_add", "error" not in r, str(r.get("error")))

        lead_id = core.leads_db[0].id
        r = json.loads(text_of(await client.call_tool("marketing_qualify", {"lead_id": lead_id})))
        check("tool: marketing_qualify", 0 <= r["qualification"]["score"] <= 100,
              str(r["qualification"]["band"]))

        r = json.loads(text_of(await client.call_tool("marketing_route_lead", {"lead_id": lead_id})))
        check("tool: marketing_route_lead", bool(r["routing"].get("queue")), str(r["routing"]))

        r = json.loads(text_of(await client.call_tool("marketing_reengagement", {})))
        check("tool: marketing_reengagement", "candidates" in r, str(list(r)[:4]))

        r = json.loads(text_of(await client.call_tool("marketing_generate_content", {
            "kind": "social_post", "property_id": pid})))
        asset_id = r["asset"]["id"]
        check("tool: marketing_generate_content", bool(asset_id) and r["asset"]["status"] == "draft",
              str(r["asset"].get("status")))

        r = json.loads(text_of(await client.call_tool("marketing_content_assets", {"status": "draft"})))
        check("tool: marketing_content_assets", r["count"] >= 1, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("marketing_content_approve", {"asset_id": asset_id})))
        check("tool: marketing_content_approve", r["asset"]["status"] == "approved", str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("marketing_campaign_plan", {
            "objective": "sell 10 units", "budget": 300_000,
            "channels": ["whatsapp", "website"]})))
        check("tool: marketing_campaign_plan", r["campaign"]["kpis"]["expected_leads"] > 0,
              str(r["campaign"].get("kpis")))

        r = json.loads(text_of(await client.call_tool("marketing_funnel", {})))
        check("tool: marketing_funnel", r.get("leads", 0) >= 1, str(r.get("leads")))

        html = text_of(await client.call_tool("marketing_portal", {"lang": "en"}))
        check("tool: marketing_portal", "AI Marketing Conductor wing" in html, str(len(html)))

        # ---------------- commercialization ----------------
        r = json.loads(text_of(await client.call_tool("commercial_products", {})))
        check("tool: commercial_products", r["count"] == 8, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("commercial_product", {"key": "mcp_for_brokers"})))
        check("tool: commercial_product", r.get("key") == "mcp_for_brokers" and "plans" in r, str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("commercial_plans", {})))
        check("tool: commercial_plans", r["count"] >= 5, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("commercial_plan", {"key": "mcp_growth"})))
        check("tool: commercial_plan", r.get("key") == "mcp_growth", str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("commercial_pricing_matrix", {})))
        check("tool: commercial_pricing_matrix", len(r.get("rows", [])) == 8, str(len(r.get("rows", []))))

        r = json.loads(text_of(await client.call_tool("commercial_recommend_package", {
            "segment": "broker", "seats": 3, "expected_calls": 3000})))
        check("tool: commercial_recommend_package", bool(r.get("recommended_plan", {}).get("plan")),
              str(r.get("recommended_plan")))

        r = json.loads(text_of(await client.call_tool("commercial_subscribe", {
            "account": "mcp-acct", "plan_key": "mcp_growth", "seats": 2})))
        check("tool: commercial_subscribe", "error" not in r, str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("commercial_subscriptions", {"account": "mcp-acct"})))
        check("tool: commercial_subscriptions", r["count"] >= 1, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("commercial_meter_usage", {
            "account": "mcp-acct", "tool": "gis_score", "units": 5000})))
        check("tool: commercial_meter_usage", "event" in r, str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("commercial_usage", {"account": "mcp-acct"})))
        check("tool: commercial_usage", r.get("total_units", 0) >= 5000, str(r.get("total_units")))

        r = json.loads(text_of(await client.call_tool("commercial_bill", {"account": "mcp-acct"})))
        check("tool: commercial_bill", r.get("total_due", 0) > 0 and len(r.get("lines", [])) >= 1,
              str(r.get("total_due")))

        r = json.loads(text_of(await client.call_tool("commercial_revenue_share", {"commission_gross": 500_000})))
        check("tool: commercial_revenue_share", "allocation" in r and "platform_share" in r["policy"],
              str(r["policy"]))

        r = json.loads(text_of(await client.call_tool("commercial_record_payout", {
            "transaction_id": "TXN-MCP", "gross_commission": 500_000, "payee": "a1", "share_pct": 0.4})))
        check("tool: commercial_record_payout", r["payout"]["amount"] == 200_000, str(r["payout"].get("amount")))

        r = json.loads(text_of(await client.call_tool("commercial_payouts", {})))
        check("tool: commercial_payouts", r["count"] >= 1, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("commercial_gtm", {})))
        check("tool: commercial_gtm", len(r.get("priorities", [])) >= 4, str(len(r.get("priorities", []))))

        html = text_of(await client.call_tool("agentic_portal", {"lang": "en"}))
        check("tool: agentic_portal", "Agentic OS" in html and "Product roadmap" in html, str(len(html)))

        html = text_of(await client.call_tool("commercial_portal", {"lang": "en"}))
        check("tool: commercial_portal", "Commercialization wing" in html, str(len(html)))

        # ---------------- productised front doors (broker / property intelligence) ----
        r = json.loads(text_of(await client.call_tool("search_contacts", {})))
        check("tool: search_contacts", r["count"] >= 1 and r["contacts"][0]["intent_score"] >= 0,
              str(r["count"]))

        r = json.loads(text_of(await client.call_tool("search_contacts",
                                                      {"lifecycle": "hot", "min_intent_score": 30})))
        check("tool: search_contacts (filtered)", r["returned"] <= r["count"], str(r["returned"]))

        r = json.loads(text_of(await client.call_tool("get_commission_projection", {})))
        check("tool: get_commission_projection",
              r["weighted_pipeline_commission"] >= 0 and "upcoming_closings" in r,
              str(r["weighted_pipeline_commission"]))

        r = json.loads(text_of(await client.call_tool("analyze_property_gis", {"property_id": pid})))
        check("tool: analyze_property_gis",
              r["grade"] in ("A", "B", "C", "D") and len(r["dimensions"]) >= 3, str(r["grade"]))

        r = json.loads(text_of(await client.call_tool("get_gis_score", {"address": "Lahore"})))
        check("tool: get_gis_score", r.get("composite_score", -1) >= 0, str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("get_accounting_snapshot", {"property_id": pid})))
        check("tool: get_accounting_snapshot", r["cap_rate"] > 0 and r["net_operating_income"] > 0,
              str(r.get("cap_rate")))

        r = json.loads(text_of(await client.call_tool("get_market_intelligence", {})))
        check("tool: get_market_intelligence",
              r["direction"] in ("expanding", "stable", "softening"), str(r["direction"]))

        r = json.loads(text_of(await client.call_tool("score_seller_intent", {"contact_id": lead_id})))
        check("tool: score_seller_intent",
              0 <= r["score"] <= 100 and r["band"] in ("ready", "warming", "curious", "cold"),
              str(r["band"]))

        r = json.loads(text_of(await client.call_tool("create_listing_draft", {"property_id": pid})))
        check("tool: create_listing_draft", r["status"] == "draft" and len(r["social_posts"]) == 4,
              str(r.get("error")))

        # ---------------- product resources & templates ----------------
        for uri, needle in (("agents://overview", "counts"),
                            ("agents://catalog", "agents"),
                            ("agents://products", "products"),
                            ("agents://smart-actions", "by_band"),
                            ("transactions://all", "transactions"),
                            ("transactions://deadlines", "count"),
                            ("intelligence://anomalies", "scanned"),
                            ("intelligence://screener", "considered"),
                            ("leasing://units", "units"),
                            ("leasing://funnel", "inquiries"),
                            ("leasing://inquiries", "count"),
                            ("marketing://routes", "routes"),
                            ("marketing://funnel", "leads"),
                            ("marketing://content", "assets"),
                            ("commercial://products", "products"),
                            ("commercial://plans", "plans"),
                            ("commercial://pricing", "rows"),
                            ("commercial://subscriptions", "subscriptions"),
                            ("commercial://gtm", "priorities"),
                            ("broker://contacts", "contacts"),
                            ("broker://commission-projection", "weighted_pipeline_commission"),
                            ("property-intelligence://market", "market_index")):
            body = await client.read_resource(uri)
            uri_text = "".join(getattr(c, "text", "") for c in body.contents)
            check(f"resource: {uri}", needle in uri_text, uri_text[:70].replace("\n", " "))

        for uri, needle in (("agent://conversational_buyer_agent", "conversational_buyer_agent"),
                            ("transaction://" + STATE["tx_id"], STATE["tx_id"]),
                            ("property-intelligence://gis/" + pid, "composite_score")):
            body = await client.read_resource(uri)
            uri_text = "".join(getattr(c, "text", "") for c in body.contents)
            check(f"resource template: {uri[:28]}", needle in uri_text, uri_text[:60].replace("\n", " "))

        for pname, pargs in (("conversational_buyer_brief", {"brief": "3 bed Lahore"}),
                             ("seller_pricing_listing", {"property_id": pid}),
                             ("transaction_close_prompt", {"tx_id": tx_id}),
                             ("agentic_workspace_brief", {}),
                             ("investment_screener_prompt", {"city": "Lahore"})):
            prompt = await client.get_prompt(pname, pargs)
            check(f"prompt: {pname}", len(prompt.messages) > 0, str(len(prompt.messages)))


# ============================================================
# 2b) Agentic products (REST)
# ============================================================


def run_geo_checks(client: TestClient) -> None:
    """Places, areas and population from the bundled geodata (offline: no Nominatim)."""
    import geo
    geo.ONLINE_LOOKUP = False
    check("geo: 'DHA 2' -> 'dha phase 2'", geo.normalize("DHA 2") == "dha phase 2", geo.normalize("DHA 2"))
    check("geo: 'Bahria Town Phase-VIII' -> 'bahria phase 8'",
          geo.normalize("Bahria Town Phase-VIII") == "bahria phase 8", geo.normalize("Bahria Town Phase-VIII"))
    check("geo: 'G13' -> 'g-13'", geo.normalize("G13 Islamabad") == "g-13 islamabad", geo.normalize("G13 Islamabad"))
    r = client.get("/geo/summary").json()
    check("GET /geo/summary (data loaded)", r.get("places", 0) > 5000 and r.get("areas", 0) > 500
          and r.get("population_cells", 0) > 5000, str(r)[:200])

    r = client.get("/places/find", params={"kind": "mall", "area": "Bahria Phase 8 Rawalpindi"})
    j = r.json()
    check("GET /places/find (malls in Bahria Phase 8)", r.status_code == 200
          and any("phase 8" in geo.normalize(a) for a in j.get("matched_areas", [])) and j.get("count", -1) >= 0, str(j)[:300])
    r = client.get("/places/find", params={"kind": "high school", "area": "DHA 2 Islamabad"})
    j = r.json()
    check("GET /places/find (high schools in DHA 2)", r.status_code == 200
          and any("DHA Phase 2" in a for a in j.get("matched_areas", []))
          and all("high" in p["name"].lower() for p in j.get("places", [])), str(j)[:300])
    r = client.get("/places/find", params={"kind": "hospital", "near": "Rawalpindi Medical University", "radius_km": 3})
    j = r.json()
    check("GET /places/find (near RMU, alias)", r.status_code == 200 and "Rawalpindi Medical" in j.get("near", "")
          and j.get("count", 0) > 0, str(j)[:300])
    r = client.get("/places/find", params={"kind": "spaceport", "area": "G-13"})
    check("GET /places/find (unknown kind -> 422)", r.status_code == 422, str(r.status_code))

    r = client.get("/search", params={"near_place": "Rawalpindi Medical University", "near_km": 3})
    j = r.json()
    np = j.get("near_place") or {}
    check("GET /search?near_place (room near RMU)", np.get("found") is True and "Rawalpindi Medical" in np.get("name", "")
          and (j["count"] > 0 or bool(j.get("nearest_outside_radius"))), str(j)[:300])
    r = client.get("/search", params={"near_place": "Atlantis Underwater City"})
    check("GET /search?near_place (unknown place)", r.json().get("near_place", {}).get("found") is False, r.text[:200])

    r = client.get("/areas/profile", params={"area": "G-13 Islamabad"})
    j = r.json()
    check("GET /areas/profile (population & development)", r.status_code == 200 and j.get("found") is True
          and j.get("population_estimate", 0) > 10_000 and j.get("development_level")
          and isinstance(j.get("nearby_housing_areas"), list), str(j)[:300])
    schemes = client.get("/schemes").json().get("schemes", [])
    lsc = next((x for x in schemes if x.get("name") == "Lahore Smart City"), None)
    if lsc:
        r = client.put(f"/schemes/{lsc['id']}", json={"development_status": "under development",
                                                      "approval_authority": "LDA", "utilities": ["electricity", "gas"]})
        check("PUT /schemes/{id} (development details)", r.status_code == 200
              and r.json().get("approval_authority") == "LDA", r.text[:200])
        r = client.put(f"/schemes/{lsc['id']}", json={"colour": "green"})
        check("PUT /schemes/{id} (unknown field -> 422)", r.status_code == 422, str(r.status_code))
    r = client.get("/areas/profile", params={"area": "Lahore Smart City"})
    ps = r.json().get("portal_scheme", {})
    check("GET /areas/profile (portal scheme details)", ps.get("approval_authority") == "LDA"
          and ps.get("development_status") == "under development", r.text[:300])
    listing = next(x for x in client.get("/search", params={"limit": 50}).json()["results"]
                   if x["title"] == "Modern 10 Marla House")
    r = client.get("/places/map", params={"listing_id": listing["id"]})
    j = r.json()
    groups = {m["group"] for m in j.get("markers", [])}
    check("GET /places/map (listing + nearby places)", r.status_code == 200 and j["focus"]["type"] == "listing"
          and {"school", "mosque", "park"} <= groups and "{z}" in j.get("tiles", {}).get("url", ""), str(j)[:300])
    r = client.get("/places/map", params={"place": "Centaurus Mall Islamabad", "kinds": "hospital,bank"})
    j = r.json()
    check("GET /places/map (named place, chosen kinds)", r.status_code == 200 and j["focus"]["type"] == "place"
          and {m["group"] for m in j["markers"]} <= {"hospital", "bank"} and j["markers"], str(j)[:300])
    r = client.get("/places/map", params={"listing_id": listing["id"], "kinds": "spaceport"})
    check("GET /places/map (unknown kind -> 422)", r.status_code == 422, str(r.status_code))
    r = client.get("/places/map")
    check("GET /places/map (nothing to show -> 422)", r.status_code == 422, str(r.status_code))
    r = client.get("/geo/locate", params={"q": "Centaurus Mall Islamabad"})
    check("GET /geo/locate", r.json().get("found") is True, r.text[:200])
    run_masterplan_checks(client)
    geo.ONLINE_LOOKUP = True


def run_masterplan_checks(client: TestClient) -> None:
    """DHA master plans (only when built locally: media/masterplans is not in git)."""
    import gis
    import masterplan
    if not masterplan.find_plan("DHA Phase II"):
        print("  [SKIP] master plans not built (masterplans/build_masterplans.py)")
        return
    r = client.get("/masterplans").json()
    check("GET /masterplans", r.get("count", 0) >= 1 and all(p.get("outline") for p in r["plans"]), str(r)[:200])
    r = client.get("/masterplans/search", params={"q": "jinnah blvd", "plan": "dha 2"}).json()
    check("GET /masterplans/search (road on DHA II)", r.get("count", 0) > 0
          and all(x["category"] == "road" and x["plan_key"] == "ph2" for x in r["results"]), str(r)[:300])
    r = client.get("/masterplans/ph2").json()
    check("GET /masterplans/{key} (summary)", r.get("plan") == "DHA Phase II" and r.get("plot_sizes")
          and "Mosque" in r.get("facilities", {}), str(r)[:300])
    r = client.get("/masterplans/DHA%20Phase%202")
    check("GET /masterplans/{name} (alias)", r.status_code == 200 and r.json().get("key") == "ph2", str(r.status_code))
    r = client.get("/masterplans/at", params={"place": "Paradise Park", "plan": "DHA Phase II"}).json()
    check("GET /masterplans/at (around a label)", "DHA Phase II" in r.get("inside_plans", []) and r.get("features"), str(r)[:300])
    r = client.get("/masterplans/view", params={"plan": "DHA Phase II", "place": "Paradise Park", "radius_m": 200})
    j = r.json()
    check("GET /masterplans/view", r.status_code == 200 and j.get("snapshot_url", "").startswith("/masterplans/ph2/snapshot.png")
          and j.get("map", {}).get("focus"), str(j)[:300])
    if (masterplan.DIR / "ph2" / "source").is_dir():
        r = client.get(j["snapshot_url"])
        check("GET /masterplans/{key}/snapshot.png", r.status_code == 200 and r.headers["content-type"] == "image/png"
              and r.content[:4] == b"\x89PNG" and len(r.content) > 10_000, f"{r.status_code} {len(r.content)}")
        check("map overlays for a point on a plan", any(o["key"] == "ph2" for o in j["map"].get("overlays", [])),
              str(j["map"].get("overlays"))[:200])
    r = client.get("/masterplans/ph2/tiles/3/0/0.png")
    check("GET /masterplans tile (empty -> 204)", r.status_code == 204, str(r.status_code))
    r = client.get("/masterplans/nope")
    check("GET /masterplans/{key} (unknown -> 404)", r.status_code == 404, str(r.status_code))
    layers = [l for l in gis.list_layers(layer_type="annotation") if l.name.startswith("DHA Phase II —")]
    check("GIS: plan labels attached as annotation layers", len(layers) == 3
          and sum(len(l.geojson["features"]) for l in layers) > 5000, str([l.name for l in layers]))
    check("GIS: plan registered as master_plan layer",
          any(l.name == "DHA Phase II — master plan" for l in gis.list_layers(layer_type="master_plan")))


def run_ai_guard_checks() -> None:
    """Rate limits / sign-in gate for the OpenAI endpoints, and OpenAI error mapping."""
    import httpx
    from fastapi import HTTPException
    from starlette.requests import Request

    import ai_guard
    import openai_voice

    def fake_request(ip: str, forwarded: str = "") -> Request:
        headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded else []
        return Request({"type": "http", "method": "POST", "path": "/", "headers": headers, "client": (ip, 5000)})

    def status_of(req: Request, bucket: str) -> int:
        try:
            ai_guard.check(req, bucket)
            return 200
        except HTTPException as exc:
            return exc.status_code

    saved = (dict(ai_guard.LIMITS), ai_guard.REQUIRE_SIGNIN, ai_guard.TRUST_PROXY)
    try:
        ai_guard.reset()
        ai_guard.LIMITS["live"] = (2, 3600)
        codes = [status_of(fake_request("10.0.0.1"), "live") for _ in range(3)]
        check("ai_guard: rate limit kicks in after the limit", codes == [200, 200, 429], str(codes))
        check("ai_guard: limits are per caller", status_of(fake_request("10.0.0.2"), "live") == 200)
        # X-Forwarded-For is ignored unless AI_TRUST_PROXY is on (it is trivially spoofed).
        check("ai_guard: spoofed X-Forwarded-For ignored",
              status_of(fake_request("10.0.0.1", "1.2.3.4"), "live") == 429)
        ai_guard.TRUST_PROXY = True
        check("ai_guard: X-Forwarded-For honoured behind a proxy",
              status_of(fake_request("10.0.0.1", "1.2.3.4"), "live") == 200)
        ai_guard.REQUIRE_SIGNIN = True
        check("ai_guard: AI_REQUIRE_SIGNIN turns guests away", status_of(fake_request("10.0.0.3"), "chat") == 401)
    finally:
        ai_guard.LIMITS.clear()
        ai_guard.LIMITS.update(saved[0])
        ai_guard.REQUIRE_SIGNIN, ai_guard.TRUST_PROXY = saved[1], saved[2]
        ai_guard.reset()

    quota = openai_voice._error(httpx.Response(429, json={"error": {"message": "quota"}}))
    check("openai_voice: OpenAI 429 -> 429", quota.status == 429, str(quota.status))
    bad_key = openai_voice._error(httpx.Response(401, json={"error": {"message": "bad key"}}))
    check("openai_voice: OpenAI 401 -> clear key message", bad_key.status == 502 and "OPENAI_API_KEY" in str(bad_key), str(bad_key))
    gateway = openai_voice._error(httpx.Response(503, text="<html>Service Unavailable</html>"))
    check("openai_voice: non-JSON error handled", gateway.status == 502 and "503" in str(gateway), str(gateway))


def run_products_rest_checks(client: TestClient) -> None:
    print("\n=== Agentic products (REST) ===")
    with _SharedClient(client):
        r = client.get("/agents/overview")
        check("GET /agents/overview", r.status_code == 200 and r.json()["counts"]["products"] == 8,
              str(r.status_code))

        r = client.get("/agents/catalog")
        check("GET /agents/catalog", r.status_code == 200 and r.json().get("count", 0) >= 20,
              str(r.status_code))

        r = client.get("/agents/smart-actions")
        check("GET /agents/smart-actions", r.status_code == 200 and r.json().get("count", 0) >= 1,
              str(r.status_code))

        r = client.get("/agents/portal")
        check("GET /agents/portal (HTML)", r.status_code == 200 and "Agentic OS" in r.text, str(r.status_code))

        r = client.get("/agents/conversational_buyer_agent")
        check("GET /agents/{key}", r.status_code == 200 and r.json().get("key") == "conversational_buyer_agent",
              str(r.status_code))

        r = client.post("/agents/run", json={"agent_key": "transaction_agent", "objective": "review"})
        check("POST /agents/run", r.status_code == 200 and r.json().get("id"), str(r.status_code))

        # --- transactions ---
        r = client.get("/transactions/stages")
        check("GET /transactions/stages", r.status_code == 200 and len(r.json()["stages"]) >= 5,
              str(r.status_code))

        r = client.post("/transactions", json={"transaction_type": "sale", "price": 30_000_000,
                                               "property_title": "REST txn"})
        tx = r.json()["transaction"]
        check("POST /transactions", r.status_code == 201 and tx["id"], str(r.status_code))

        r = client.get(f"/transactions/{tx['id']}/progress")
        check("GET /transactions/{id}/progress", r.status_code == 200 and "progress_pct" in r.json(),
              str(r.status_code))

        r = client.post("/transactions/terms/extract",
                        json={"text": "Price PKR 5,000,000. Commission 2%. Possession 2026-12-01."})
        check("POST /transactions/terms/extract", r.status_code == 200 and r.json().get("term_count", 0) >= 1,
              str(r.status_code))

        r = client.post(f"/transactions/{tx['id']}/close", json={})
        check("POST /transactions/{id}/close", r.status_code == 200
              and r.json().get("balanced") is True, str(r.status_code))

        r = client.post(f"/transactions/{tx['id']}/report")
        check("POST /transactions/{id}/report (HTML)", r.status_code == 200
              and "Transaction summary" in r.text, str(r.status_code))

        # --- intelligence ---
        r = client.post("/intelligence/buyer/parse", json={"text": "3 bed house Lahore 3 crore"})
        check("POST /intelligence/buyer/parse", r.status_code == 200 and r.json().get("bedrooms") == 3,
              str(r.status_code))

        r = client.get("/intelligence/buyer/anomalies")
        check("GET /intelligence/buyer/anomalies", r.status_code == 200 and r.json().get("scanned", 0) >= 1,
              str(r.status_code))

        r = client.get("/intelligence/seller/cma/" + core.properties_db[0].id)
        check("GET /intelligence/seller/cma/{id}", r.status_code == 200
              and r.json().get("price_range", {}).get("target", 0) > 0, str(r.status_code))

        r = client.post("/intelligence/investment/underwrite",
                        json={"purchase_price": 20_000_000, "monthly_rent": 150_000})
        check("POST /intelligence/investment/underwrite", r.status_code == 200
              and r.json()["returns"]["cap_rate"] > 0, str(r.status_code))

        r = client.get("/intelligence/investment/screen", params={"min_cap_rate": 0.02})
        check("GET /intelligence/investment/screen", r.status_code == 200
              and r.json().get("passed", 0) >= 1, str(r.status_code))

        r = client.post("/intelligence/investment/report", json={})
        check("POST /intelligence/investment/report (HTML)", r.status_code == 200
              and "Top risk-adjusted picks" in r.text, str(r.status_code))

        # --- leasing ---
        r = client.get("/leasing/units")
        check("GET /leasing/units", r.status_code == 200 and r.json().get("count", 0) >= 1, str(r.status_code))

        r = client.get("/leasing/rent-floor", params={"monthly_holding_cost": 70_000})
        check("GET /leasing/rent-floor", r.status_code == 200 and r.json()["rent_floor"] > 70_000,
              str(r.status_code))

        r = client.post("/leasing/inquiries", json={"message": "Is it available?",
                                                    "unit_id": core.leasing.units_db[0].id})
        check("POST /leasing/inquiries", r.status_code == 201 and r.json().get("intent") == "availability",
              str(r.status_code))

        r = client.get("/leasing/funnel")
        check("GET /leasing/funnel", r.status_code == 200 and r.json().get("inquiries", 0) >= 1,
              str(r.status_code))

        r = client.get("/leasing/portal")
        check("GET /leasing/portal (HTML)", r.status_code == 200 and "Autonomous Leasing wing" in r.text,
              str(r.status_code))

        # --- marketing ---
        r = client.post("/marketing/qualify/" + core.leads_db[0].id)
        check("POST /marketing/qualify/{lead}", r.status_code == 200
              and "qualification" in r.json(), str(r.status_code))

        r = client.get("/marketing/funnel")
        check("GET /marketing/funnel", r.status_code == 200 and r.json().get("leads", 0) >= 1, str(r.status_code))

        r = client.post("/marketing/content", json={"kind": "social_post",
                                                    "property_id": core.properties_db[0].id})
        check("POST /marketing/content", r.status_code == 201 and r.json()["asset"]["status"] == "draft",
              str(r.status_code))

        r = client.get("/marketing/portal")
        check("GET /marketing/portal (HTML)", r.status_code == 200
              and "AI Marketing Conductor wing" in r.text, str(r.status_code))

        # --- commercial ---
        r = client.get("/commercial/products")
        check("GET /commercial/products", r.status_code == 200 and r.json().get("count") == 8, str(r.status_code))

        r = client.get("/commercial/pricing")
        check("GET /commercial/pricing", r.status_code == 200 and len(r.json().get("rows", [])) == 8,
              str(r.status_code))

        r = client.post("/commercial/subscribe", json={"account": "rest-check", "plan_key": "mcp_growth"})
        check("POST /commercial/subscribe", r.status_code == 201, str(r.status_code))

        r = client.post("/commercial/meter", json={"account": "rest-check", "tool": "gis_score", "units": 5000})
        check("POST /commercial/meter", r.status_code == 201, str(r.status_code))

        r = client.get("/commercial/bill/rest-check")
        check("GET /commercial/bill/{account}", r.status_code == 200 and r.json().get("total_due", 0) > 0,
              str(r.status_code))

        r = client.post("/commercial/revenue-share", json={"commission_gross": 500_000})
        check("POST /commercial/revenue-share", r.status_code == 200
              and "allocation" in r.json(), str(r.status_code))

        r = client.get("/commercial/portal")
        check("GET /commercial/portal (HTML)", r.status_code == 200 and "Commercialization wing" in r.text,
              str(r.status_code))

        # --- product surfaces (broker + property intelligence) ---
        pid = core.properties_db[0].id
        lead_id = core.leads_db[0].id

        r = client.get("/broker/contacts")
        check("GET /broker/contacts", r.status_code == 200 and r.json().get("count", 0) >= 1,
              str(r.status_code))

        r = client.get("/broker/commission-projection")
        check("GET /broker/commission-projection", r.status_code == 200
              and "weighted_pipeline_commission" in r.json(), str(r.status_code))

        r = client.get("/broker/property-gis", params={"property_id": pid})
        check("GET /broker/property-gis", r.status_code == 200
              and r.json().get("grade") in ("A", "B", "C", "D"), str(r.status_code))

        r = client.get("/broker/listing-draft/" + pid)
        check("GET /broker/listing-draft/{id}", r.status_code == 200
              and r.json().get("status") == "draft", str(r.status_code))

        r = client.get("/property-intelligence/gis-score", params={"address": "Lahore"})
        check("GET /property-intelligence/gis-score", r.status_code == 200
              and "composite_score" in r.json(), str(r.status_code))

        r = client.get("/property-intelligence/accounting-snapshot/" + pid)
        check("GET /property-intelligence/accounting-snapshot/{id}", r.status_code == 200
              and r.json().get("cap_rate", 0) > 0, str(r.status_code))

        r = client.get("/property-intelligence/market-intelligence")
        check("GET /property-intelligence/market-intelligence", r.status_code == 200
              and r.json().get("direction") in ("expanding", "stable", "softening"),
              str(r.status_code))

        r = client.get("/property-intelligence/seller-intent/" + lead_id)
        check("GET /property-intelligence/seller-intent/{id}", r.status_code == 200
              and "band" in r.json(), str(r.status_code))

        # --- cross-check: MCP-created transaction is visible over REST ---
        r = client.get("/transactions/" + STATE["tx_id"])
        check("cross: MCP transaction visible over REST", r.status_code == 200
              and r.json().get("id") == STATE["tx_id"], str(r.status_code))


# ============================================================
# 1d) Tools & utilities (MCP)
# ============================================================


def _tiny_jpeg_b64() -> str:
    """A minimal JPEG (SOI + SOS + EOI) — enough for an EXIF GPS round-trip."""
    return base64.b64encode(b"\xff\xd8\xff\xda\x00\x08" + b"\x00" * 8 + b"\xff\xd9").decode()


def _photo_jpeg_b64() -> str:
    """A minimal JPEG carrying a real SOF0 (1x1 px) so it can be embedded in a PDF."""
    sof0 = b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00"
    sos = b"\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00"
    return base64.b64encode(b"\xff\xd8" + sof0 + sos + b"\x00\x01\x02" + b"\xff\xd9").decode()


async def run_tools_checks() -> None:
    print("\n=== Tools & Utilities (MCP) ===")
    async with Client(core.mcp) as client:
        r = json.loads(text_of(await client.call_tool("tools_overview", {})))
        check("tool: tools_overview", r["counts"]["tools"] == len(core.tools.TOOL_CATALOG)
              and r["counts"]["categories"] == 6, str(r["counts"]))

        r = json.loads(text_of(await client.call_tool("tools_categories", {})))
        check("tool: tools_categories", r["count"] == 6, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("tools_catalog", {"category": "calculators"})))
        check("tool: tools_catalog (calculators)", r["count"] >= 10, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("tool_get", {"key": "georeference"})))
        check("tool: tool_get", r.get("name") == "Georeference a Plan", str(r.get("name")))

        r = json.loads(text_of(await client.call_tool("tool_calculators", {})))
        check("tool: tool_calculators", r["count"] == 12, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("tool_mortgage_calculator", {
            "price": 10000000, "down_payment": 2000000, "annual_rate": 0.12, "years": 15})))
        check("tool: tool_mortgage_calculator", r.get("monthly_payment", 0) > 0
              and r.get("down_payment_pct") == 20.0, str(r.get("monthly_payment")))

        r = json.loads(text_of(await client.call_tool("tool_rental_yield", {
            "price": 10000000, "monthly_rent": 50000})))
        check("tool: tool_rental_yield", r.get("gross_yield_pct") == 6.0, str(r.get("gross_yield_pct")))

        r = json.loads(text_of(await client.call_tool("tool_transfer_costs", {"price": 10000000})))
        check("tool: tool_transfer_costs", r.get("total_transfer_cost", 0) > 0, str(r.get("total_transfer_cost")))

        r = json.loads(text_of(await client.call_tool("tool_capital_gains_tax", {
            "gain": 1000000, "holding_years": 4, "filer": True})))
        check("tool: tool_capital_gains_tax", r.get("rate_pct") == 5.0, str(r.get("rate_pct")))

        r = json.loads(text_of(await client.call_tool("tool_joint_investment", {
            "partners": [{"name": "a", "capital": 300}, {"name": "b", "capital": 100}], "total_profit": 400})))
        check("tool: tool_joint_investment", r["partners"][0]["profit"] == 300.0, str(r["partners"][0]))

        r = json.loads(text_of(await client.call_tool("tool_area_convert", {
            "value": 1, "from_unit": "kanal", "to_unit": "marla"})))
        check("tool: tool_area_convert", r["result"]["value"] == 20.0, str(r["result"]))

        r = json.loads(text_of(await client.call_tool("tool_construction_cost", {
            "covered_area": 2000, "city": "Lahore"})))
        check("tool: tool_construction_cost", r.get("cost", {}).get("total", 0) > 0, str(list(r)[:5]))

        r = json.loads(text_of(await client.call_tool("tool_crs_catalog", {})))
        check("tool: tool_crs_catalog", r["count"] == 5, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("tool_map_measure", {
            "coords": [[31.52, 74.35], [31.53, 74.35], [31.53, 74.36]]})))
        check("tool: tool_map_measure", r.get("area_sqft", 0) > 0 and r.get("perimeter_m", 0) > 0,
              str(r.get("area_sqft")))

        r = json.loads(text_of(await client.call_tool("tool_georeference", {"control_points": [
            {"image": [0, 0], "geo": [31.0, 74.0]}, {"image": [100, 0], "geo": [31.0, 74.001]},
            {"image": [0, 100], "geo": [31.001, 74.0]}, {"image": [100, 100], "geo": [31.001, 74.001]}]})))
        check("tool: tool_georeference", r.get("model") == "affine" and r.get("rmse_m", 999) < 15, str(r.get("rmse_m")))

        r = json.loads(text_of(await client.call_tool("tool_export_geodata", {
            "features": [{"kind": "polygon", "coords": [[31.52, 74.35], [31.53, 74.35], [31.53, 74.36]],
                         "name": "P"}]})))
        check("tool: tool_export_geodata", r.get("format") == "geojson" and r.get("features") == 1, str(r.get("format")))

        geo = json.dumps({"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": {"type": "Polygon",
             "coordinates": [[[74.35, 31.52], [74.35, 31.53], [74.36, 31.53], [74.35, 31.52]]]},
             "properties": {}}]})
        r = json.loads(text_of(await client.call_tool("tool_import_geodata", {"text": geo})))
        check("tool: tool_import_geodata", r.get("count") == 1, str(r.get("count")))

        r = json.loads(text_of(await client.call_tool("tool_locate_nearby", {
            "origin": [31.5204, 74.3587], "radius_m": 5000})))
        check("tool: tool_locate_nearby", "nearest" in r, str(r.get("count")))

        r = json.loads(text_of(await client.call_tool("tool_cad_formats", {})))
        check("tool: tool_cad_formats", r["count"] == 5, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("tool_dxf_preview", {"text":
            "0\nSECTION\n0\nLINE\n8\nW\n10\n0\n20\n0\n11\n10\n21\n10\n0\nENDSEC\n0\nEOF\n"})))
        check("tool: tool_dxf_preview", r.get("svg", "").startswith("<svg") and r.get("entity_count") == 1,
              str(r.get("by_type")))

        jpeg = _tiny_jpeg_b64()
        r = json.loads(text_of(await client.call_tool("tool_write_photo_gps", {
            "image_base64": jpeg, "latitude": 31.5204, "longitude": 74.3587, "altitude": 215.5})))
        check("tool: tool_write_photo_gps", r.get("written") is True, str(r.get("error")))
        tagged = r.get("image_base64")

        r = json.loads(text_of(await client.call_tool("tool_read_photo_gps", {"image_base64": tagged})))
        check("tool: tool_read_photo_gps", abs(r.get("latitude", 0) - 31.5204) < 1e-5
              and abs(r.get("longitude", 0) - 74.3587) < 1e-5, str(r))

        r = json.loads(text_of(await client.call_tool("tool_text_to_pdf", {"title": "T", "lines": ["a", "b"]})))
        check("tool: tool_text_to_pdf", r.get("pdf_base64", "").startswith("JVBER") and r.get("pages") == 1,
              str(r.get("pages")))

        r = json.loads(text_of(await client.call_tool("tool_pdf_info", {"pdf_base64": r["pdf_base64"]})))
        check("tool: tool_pdf_info", r.get("pages") == 1, str(r.get("pages")))

        r = json.loads(text_of(await client.call_tool("tool_document_tools", {})))
        check("tool: tool_document_tools", r["count"] >= 10, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("tool_hijri_from_gregorian", {"on": "2024-04-10"})))
        check("tool: tool_hijri_from_gregorian", r.get("hijri_month_name") == "Shawwal", str(r.get("hijri")))

        r = json.loads(text_of(await client.call_tool("tool_gregorian_from_hijri", {
            "year": 1445, "month": 10, "day": 1})))
        check("tool: tool_gregorian_from_hijri", r.get("gregorian") == "2024-04-10", str(r.get("gregorian")))

        r = json.loads(text_of(await client.call_tool("tool_pakistan_holidays", {"year": 2026})))
        check("tool: tool_pakistan_holidays", r["count"] > 5, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("tool_calendar_ics", {
            "events": [{"date": "2026-08-14", "title": "Independence Day"}]})))
        check("tool: tool_calendar_ics", "BEGIN:VCALENDAR" in r.get("ics", "") and r.get("events") == 1,
              str(r.get("events")))

        r = json.loads(text_of(await client.call_tool("tool_milestone_calendar", {
            "start_date": "2026-01-01", "covered_area": 2000})))
        check("tool: tool_milestone_calendar", r.get("total_days", 0) > 0 and len(r.get("events", [])) > 0,
              str(r.get("handover_date")))

        r = json.loads(text_of(await client.call_tool("tool_property_comparison", {"properties": [
            {"name": "A", "price": 10000000, "area_sqft": 1000, "monthly_rent": 50000},
            {"name": "B", "price": 12000000, "area_sqft": 1200, "monthly_rent": 70000}]})))
        check("tool: tool_property_comparison", r.get("count") == 2 and r.get("best_yield") in ("A", "B"), str(r))

        r = json.loads(text_of(await client.call_tool("tool_rows_to_csv", {"rows": [{"a": 1, "b": 2}]})))
        check("tool: tool_rows_to_csv", r.get("csv", "").startswith("a,b"), str(r.get("csv"))[:40])

        r = json.loads(text_of(await client.call_tool("tool_rows_to_markdown", {"rows": [{"a": 1, "b": 2}]})))
        check("tool: tool_rows_to_markdown", "| a | b |" in r.get("markdown", ""), "")

        r = json.loads(text_of(await client.call_tool("tool_save_project", {
            "name": "mcp-proj", "tool": "mortgage", "inputs": {}})))
        STATE["proj_id"] = r.get("id")
        check("tool: tool_save_project", bool(STATE["proj_id"]), str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("tool_projects", {})))
        check("tool: tool_projects", any(p["id"] == STATE["proj_id"] for p in r.get("projects", [])),
              str(r.get("count")))

        r = json.loads(text_of(await client.call_tool("tool_project_delete", {"project_id": STATE["proj_id"]})))
        check("tool: tool_project_delete", r.get("deleted") is True, str(r))

        html = text_of(await client.call_tool("tools_portal", {"lang": "en"}))
        check("tool: tools_portal (HTML)", "Tools" in html and "tc-grid" in html and len(html) > 5000,
              f"chars={len(html)}")

        r = json.loads(text_of(await client.call_tool("portal_settings", {"action": "get"})))
        check("tool: portal_settings includes tools", "tools" in r, str(list(r)[:6]))


# ============================================================
# 1e) Tools & utilities (REST)
# ============================================================


def run_tools_rest_checks(client: TestClient) -> None:
    print("\n=== Tools & Utilities (REST) ===")
    with _SharedClient(client):
        r = client.get("/tools/overview")
        check("GET /tools/overview", r.status_code == 200
              and r.json()["counts"]["tools"] == len(core.tools.TOOL_CATALOG), str(r.status_code))

        r = client.get("/tools/categories")
        check("GET /tools/categories", r.status_code == 200 and r.json()["count"] == 6, str(r.status_code))

        r = client.get("/tools/catalog", params={"category": "gis"})
        check("GET /tools/catalog?category=gis", r.status_code == 200 and r.json()["count"] >= 5, str(r.status_code))

        r = client.get("/tools/catalog/mortgage")
        check("GET /tools/catalog/{key}", r.status_code == 200 and r.json()["name"] == "Mortgage Calculator",
              str(r.status_code))

        r = client.get("/tools/convert/area", params={"value": 10, "from_unit": "marla", "to_unit": "sqft"})
        check("GET /tools/convert/area", r.status_code == 200 and r.json()["result"]["value"] == 2722.5,
              str(r.status_code))

        r = client.get("/tools/convert/area-table", params={"value": 1, "from_unit": "kanal"})
        check("GET /tools/convert/area-table", r.status_code == 200 and r.json()["conversions"]["marla"] == 20.0,
              str(r.status_code))

        r = client.get("/tools/plot/dimensions", params={"area": 10, "from_unit": "marla"})
        check("GET /tools/plot/dimensions", r.status_code == 200 and r.json()["area_sqft"] > 0, str(r.status_code))

        r = client.get("/tools/plot/studio", params={"value": 10, "covered_area": 2000})
        check("GET /tools/plot/studio", r.status_code == 200 and r.json()["diagram_svg"].startswith("<svg"),
              str(r.status_code))

        r = client.get("/tools/calculators")
        check("GET /tools/calculators", r.status_code == 200 and r.json()["count"] == 12, str(r.status_code))

        r = client.post("/tools/calculators/mortgage", json={"price": 10000000, "down_payment": 2000000,
                                                             "annual_rate": 0.12, "years": 15})
        check("POST /tools/calculators/mortgage", r.status_code == 200 and r.json()["monthly_payment"] > 0,
              str(r.status_code))

        r = client.post("/tools/calculators/installment", json={"price": 10000000, "down_payment": 2000000,
                                                                "months": 36})
        check("POST /tools/calculators/installment", r.status_code == 200 and r.json()["monthly_installment"] > 0,
              str(r.status_code))

        r = client.post("/tools/calculators/rental-yield", json={"price": 10000000, "monthly_rent": 50000})
        check("POST /tools/calculators/rental-yield", r.status_code == 200 and r.json()["gross_yield_pct"] == 6.0,
              str(r.status_code))

        r = client.post("/tools/calculators/appreciation", json={"current_value": 1000000, "cagr": 0.1, "years": 5})
        check("POST /tools/calculators/appreciation", r.status_code == 200 and len(r.json()["series"]) == 6,
              str(r.status_code))

        r = client.post("/tools/calculators/price-per-unit", json={"price": 10000000, "area": 1000})
        check("POST /tools/calculators/price-per-unit", r.status_code == 200
              and r.json()["price_per_sqft"] == 10000.0, str(r.status_code))

        r = client.post("/tools/calculators/transfer-costs", json={"price": 10000000})
        check("POST /tools/calculators/transfer-costs", r.status_code == 200
              and r.json()["total_transfer_cost"] > 0, str(r.status_code))

        r = client.post("/tools/calculators/commission", json={"price": 10000000})
        check("POST /tools/calculators/commission", r.status_code == 200 and r.json()["commission"] == 200000.0,
              str(r.status_code))

        r = client.post("/tools/calculators/capital-gains", json={"gain": 1000000, "holding_years": 4})
        check("POST /tools/calculators/capital-gains", r.status_code == 200 and r.json()["rate_pct"] == 5.0,
              str(r.status_code))

        r = client.post("/tools/calculators/joint-investment", json={"partners": [
            {"name": "a", "capital": 300}, {"name": "b", "capital": 100}], "total_profit": 400})
        check("POST /tools/calculators/joint-investment", r.status_code == 200
              and r.json()["partners"][0]["profit"] == 300.0, str(r.status_code))

        r = client.post("/tools/calculators/rent-vs-buy", json={"price": 10000000, "monthly_rent": 40000})
        check("POST /tools/calculators/rent-vs-buy", r.status_code == 200 and r.json()["projected_value"] > 0,
              str(r.status_code))

        r = client.post("/tools/calculators/construction-cost", json={"covered_area": 2000, "city": "Lahore"})
        check("POST /tools/calculators/construction-cost", r.status_code == 200
              and r.json()["cost"]["total"] > 0, str(r.status_code))

        r = client.post("/tools/calculators/material-quantities", json={"covered_area": 2000})
        check("POST /tools/calculators/material-quantities", r.status_code == 200, str(r.status_code))

        r = client.post("/tools/calculators/build-timeline", json={"covered_area": 2000})
        check("POST /tools/calculators/build-timeline", r.status_code == 200 and r.json()["total_days"] > 0,
              str(r.status_code))

        r = client.get("/tools/gis/crs")
        check("GET /tools/gis/crs", r.status_code == 200 and r.json()["count"] == 5, str(r.status_code))

        r = client.post("/tools/gis/measure", json={"coords": [[31.52, 74.35], [31.53, 74.35], [31.53, 74.36]]})
        check("POST /tools/gis/measure", r.status_code == 200 and r.json()["area_sqft"] > 0, str(r.status_code))

        r = client.post("/tools/gis/polygon-area", json={"coords": [[31.52, 74.35], [31.53, 74.35], [31.53, 74.36]],
                                                         "unit": "marla"})
        check("POST /tools/gis/polygon-area", r.status_code == 200 and r.json()["value"] > 0, str(r.status_code))

        r = client.post("/tools/gis/georeference", json={"control_points": [
            {"image": [0, 0], "geo": [31.0, 74.0]}, {"image": [100, 0], "geo": [31.0, 74.001]},
            {"image": [0, 100], "geo": [31.001, 74.0]}]})
        check("POST /tools/gis/georeference", r.status_code == 200 and r.json()["model"] == "affine",
              str(r.status_code))

        r = client.post("/tools/gis/transform", json={"matrix": {"a": 0.00001, "b": 0.0, "c": 74.0,
                                                                 "d": 0.0, "e": 0.00001, "f": 31.0},
                                                      "x": 50, "y": 100})
        check("POST /tools/gis/transform", r.status_code == 200 and "lat" in r.json(), str(r.status_code))

        r = client.post("/tools/gis/aerial-compare", json={"scenes": [{"date": "2020-01-01", "resolution_m": 0.5},
                                                                      {"date": "2024-01-01", "resolution_m": 0.3}]})
        check("POST /tools/gis/aerial-compare", r.status_code == 200 and r.json()["count"] == 2, str(r.status_code))

        r = client.post("/tools/gis/export", json={"features": [{"kind": "polygon", "coords": [
            [31.52, 74.35], [31.53, 74.35], [31.53, 74.36]]}]})
        check("POST /tools/gis/export", r.status_code == 200 and r.json()["format"] == "geojson", str(r.status_code))

        r = client.post("/tools/gis/import", json={"text": json.dumps({"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [74.3587, 31.5204]},
             "properties": {}}]})})
        check("POST /tools/gis/import", r.status_code == 200 and r.json()["count"] == 1, str(r.status_code))

        r = client.post("/tools/gis/nearby", json={"origin": [31.5204, 74.3587], "radius_m": 5000})
        check("POST /tools/gis/nearby", r.status_code == 200 and "nearest" in r.json(), str(r.status_code))

        r = client.get("/tools/cad/formats")
        check("GET /tools/cad/formats", r.status_code == 200 and r.json()["count"] == 5, str(r.status_code))

        r = client.post("/tools/cad/inspect", json={"filename": "plan.dwg",
                                                    "head_base64": base64.b64encode(b"AC1018xxxx").decode()})
        check("POST /tools/cad/inspect", r.status_code == 200 and r.json()["detected_format"] == "DWG",
              str(r.status_code))

        r = client.post("/tools/cad/dxf-preview", json={"text":
            "0\nSECTION\n0\nLINE\n8\nW\n10\n0\n20\n0\n11\n10\n21\n10\n0\nENDSEC\n0\nEOF\n"})
        check("POST /tools/cad/dxf-preview", r.status_code == 200 and r.json()["svg"].startswith("<svg"),
              str(r.status_code))

        r = client.post("/tools/cad/compare-revisions", json={"a_entities": [{"type": "line",
                                                                             "points": [[0, 0], [10, 10]]}],
                                                              "b_entities": []})
        check("POST /tools/cad/compare-revisions", r.status_code == 200 and r.json()["removed"] == 1,
              str(r.status_code))

        r = client.post("/tools/cad/layout-sheet", json={"title": "Plot 12", "plot_length_ft": 50,
                                                         "plot_width_ft": 30})
        check("POST /tools/cad/layout-sheet", r.status_code == 200 and r.json()["svg"].startswith("<svg"),
              str(r.status_code))

        jpeg = _tiny_jpeg_b64()
        r = client.post("/tools/photo/write-gps", json={"image_base64": jpeg, "latitude": 31.5204,
                                                        "longitude": 74.3587})
        check("POST /tools/photo/write-gps", r.status_code == 200 and r.json()["written"] is True, str(r.status_code))
        tagged = r.json()["image_base64"]

        r = client.post("/tools/photo/read-gps", json={"image_base64": tagged})
        check("POST /tools/photo/read-gps", r.status_code == 200 and abs(r.json()["latitude"] - 31.5204) < 1e-5,
              str(r.status_code))

        r = client.post("/tools/photo/geotag-batch", json={"photos": [{"name": "a", "image_base64": jpeg},
                                                                      {"name": "b", "image_base64": jpeg}],
                                                           "latitude": 31.52, "longitude": 74.35})
        check("POST /tools/photo/geotag-batch", r.status_code == 200 and r.json()["tagged"] == 2, str(r.status_code))

        r = client.post("/tools/photo/report", json={"photos": [{"name": "a", "latitude": 31.52, "longitude": 74.35,
                                                                 "timestamp": "2026-05-01T10:00:00"}]})
        check("POST /tools/photo/report", r.status_code == 200 and r.json()["count"] == 1, str(r.status_code))

        r = client.get("/tools/photo/privacy-check", params={"latitude": 31.5204, "longitude": 74.3587})
        check("GET /tools/photo/privacy-check", r.status_code == 200 and "recommendation" in r.json(),
              str(r.status_code))

        r = client.post("/tools/documents/text-to-pdf", json={"title": "T", "lines": ["a", "b"]})
        check("POST /tools/documents/text-to-pdf", r.status_code == 200
              and r.json()["pdf_base64"].startswith("JVBER"), str(r.status_code))
        pdf = r.json()["pdf_base64"]

        r = client.post("/tools/documents/images-to-pdf", json={"images": [{"name": "p.jpg",
                                                                           "image_base64": _photo_jpeg_b64()}]})
        check("POST /tools/documents/images-to-pdf", r.status_code == 200 and r.json()["pages"] == 1,
              str(r.text)[:120])

        r = client.post("/tools/documents/brochure", json={"title": "Villa", "subtitle": "DHA",
                                                           "sections": [{"heading": "Overview",
                                                                         "lines": ["3 bed"]}]})
        check("POST /tools/documents/brochure", r.status_code == 200
              and r.json()["pdf_base64"].startswith("JVBER"), str(r.status_code))

        r = client.post("/tools/documents/pdf-info", json={"pdf_base64": pdf})
        check("POST /tools/documents/pdf-info", r.status_code == 200 and r.json()["pages"] == 1, str(r.status_code))

        r = client.get("/tools/documents/resize-plan", params={"width": 3000, "height": 2000})
        check("GET /tools/documents/resize-plan", r.status_code == 200 and r.json()["needed"] is True,
              str(r.status_code))

        r = client.get("/tools/calendar/hijri", params={"on": "2024-03-12"})
        check("GET /tools/calendar/hijri", r.status_code == 200 and r.json()["hijri_year"] == 1445, str(r.status_code))

        r = client.get("/tools/calendar/gregorian", params={"year": 1445, "month": 10, "day": 1})
        check("GET /tools/calendar/gregorian", r.status_code == 200 and r.json()["gregorian"] == "2024-04-10",
              str(r.status_code))

        r = client.get("/tools/calendar/occasions", params={"year": 2026})
        check("GET /tools/calendar/occasions", r.status_code == 200 and r.json()["count"] > 0, str(r.status_code))

        r = client.get("/tools/calendar/holidays", params={"year": 2026})
        check("GET /tools/calendar/holidays", r.status_code == 200 and r.json()["count"] > 5, str(r.status_code))

        r = client.post("/tools/calendar/ics", json={"events": [{"date": "2026-08-14", "title": "Independence Day"}]})
        check("POST /tools/calendar/ics", r.status_code == 200 and "BEGIN:VCALENDAR" in r.json()["ics"],
              str(r.status_code))

        r = client.post("/tools/calendar/reminders", json={"events": [{"title": "Possession",
                                                                       "date": "2026-12-31", "type": "possession"}]})
        check("POST /tools/calendar/reminders", r.status_code == 200 and r.json()["count"] == 1, str(r.status_code))

        r = client.post("/tools/calendar/milestones", json={"start_date": "2026-01-01", "covered_area": 2000})
        check("POST /tools/calendar/milestones", r.status_code == 200 and r.json()["total_days"] > 0,
              str(r.status_code))

        r = client.post("/tools/calendar/possession", json={"start_date": "2026-01-01", "total_price": 10000000,
                                                            "down_payment": 2000000, "months": 24})
        check("POST /tools/calendar/possession", r.status_code == 200 and r.json()["installments"] == 24,
              str(r.status_code))

        r = client.post("/tools/reports/comparison", json={"properties": [
            {"name": "A", "price": 10000000, "area_sqft": 1000, "monthly_rent": 50000}]})
        check("POST /tools/reports/comparison", r.status_code == 200 and r.json()["best_value"] == "A",
              str(r.status_code))

        r = client.post("/tools/reports/investment-summary", json={"initial_investment": 1000000,
                                                                   "annual_cash_flow": 100000, "hold_years": 5,
                                                                   "terminal_value": 1500000})
        check("POST /tools/reports/investment-summary", r.status_code == 200, str(r.status_code))

        r = client.post("/tools/reports/plot-inventory", json={"properties": [{"name": "P", "area_sqft": 2722.5,
                                                                               "price": 5000000}]})
        check("POST /tools/reports/plot-inventory", r.status_code == 200 and r.json()["count"] == 1, str(r.status_code))

        r = client.post("/tools/reports/csv", json={"rows": [{"a": 1, "b": 2}]})
        check("POST /tools/reports/csv", r.status_code == 200 and r.json()["csv"].startswith("a,b"), str(r.status_code))

        r = client.post("/tools/reports/markdown", json={"rows": [{"a": 1, "b": 2}]})
        check("POST /tools/reports/markdown", r.status_code == 200 and "| a | b |" in r.json()["markdown"],
              str(r.status_code))

        r = client.get("/tools/projects")
        check("GET /tools/projects", r.status_code == 200 and r.json()["count"] >= 1, str(r.status_code))

        r = client.post("/tools/projects", json={"name": "rest-proj", "tool": "rental_yield", "inputs": {}})
        check("POST /tools/projects", r.status_code == 200 and r.json().get("id"), str(r.status_code))
        pid = r.json()["id"]

        r = client.get("/tools/projects/" + pid)
        check("GET /tools/projects/{id}", r.status_code == 200 and r.json()["id"] == pid, str(r.status_code))

        r = client.delete("/tools/projects/" + pid)
        check("DELETE /tools/projects/{id}", r.status_code == 200 and r.json()["deleted"] is True, str(r.status_code))

        r = client.get("/tools/portal")
        check("GET /tools/portal (HTML)", r.status_code == 200 and "Tools" in r.text and "tc-grid" in r.text,
              str(r.status_code))

        r = client.get("/tools/portal.html", params={"lang": "ur", "theme": "dark"})
        check("GET /tools/portal.html (ur/dark)", r.status_code == 200 and 'dir="rtl"' in r.text, str(r.status_code))


# ============================================================
# 1f) PMO / project management (MCP)
# ============================================================


async def run_pmo_checks() -> None:
    print("\n=== PMO / Project Management (MCP) ===")
    async with Client(core.mcp) as client:
        r = json.loads(text_of(await client.call_tool("pmo_overview", {})))
        check("pmo: pmo_overview", r["counts"]["projects"] >= 1 and r["counts"]["tasks"] >= 16,
              str(r["counts"]["projects"]))

        r = json.loads(text_of(await client.call_tool("pmo_capabilities", {})))
        check("pmo: pmo_capabilities", r["count"] >= 15, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("pm_project_types", {})))
        check("pmo: pm_project_types", r["count"] == 8, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("pm_phase_templates",
                                                      {"project_type": "construction"})))
        check("pmo: pm_phase_templates", len(r["phases"]) == 9, str(len(r.get("phases", []))))

        r = json.loads(text_of(await client.call_tool("pm_projects", {})))
        check("pmo: pm_projects (seeded)", r["count"] >= 1, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("pm_create_project", {
            "name": "MCP Test Block", "project_type": "construction", "city": "Lahore",
            "budget": 120000000, "contract_value": 138000000, "start_date": "2026-03-02",
            "status": "active"})))
        STATE["pm_id"] = r["project"]["id"]
        check("pmo: pm_create_project", r["created"] and r["phases"] == 9 and r["tasks"] == 16,
              str(r.get("error") or r.get("tasks")))
        pid = STATE["pm_id"]

        r = json.loads(text_of(await client.call_tool("pm_project", {"project_id": pid})))
        check("pmo: pm_project", r["project"]["id"] == pid and r["task_count"] == 16,
              str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("pm_phases", {"project_id": pid})))
        check("pmo: pm_phases", r["count"] == 9 and r["phases"][0]["weight_pct"] > 0, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("pm_milestones", {"project_id": pid})))
        check("pmo: pm_milestones (seeded)", r["count"] == 3, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("pm_add_milestone", {
            "project_id": pid, "name": "Slab-1 complete", "planned_date": "2026-05-01",
            "billable_amount": 5000000})))
        check("pmo: pm_add_milestone", r["created"], str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("pm_tasks", {"project_id": pid})))
        check("pmo: pm_tasks", r["count"] == 16 and "planned_start" in r["tasks"][0], str(r["count"]))
        STATE["pm_task"] = r["tasks"][0]["id"]

        r = json.loads(text_of(await client.call_tool("pm_add_task", {
            "project_id": pid, "name": "Handover snag list", "duration_days": 5})))
        check("pmo: pm_add_task", r["created"], str(r.get("error")))
        extra_task = r["task"]["id"]

        r = json.loads(text_of(await client.call_tool("pm_task", {"task_id": STATE["pm_task"]})))
        check("pmo: pm_task", "planned_start" in r and "float_days" in r, str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("pm_update_task", {
            "task_id": STATE["pm_task"], "updates": {"progress_pct": 60, "status": "in_progress"}})))
        check("pmo: pm_update_task", r["task"]["progress_pct"] == 60.0, str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("pm_schedule", {"project_id": pid})))
        check("pmo: pm_schedule", r["start"] == "2026-03-02" and r["duration_days"] > 100
              and len(r["critical_path"]) > 0, str(r.get("duration_days")))

        r = json.loads(text_of(await client.call_tool("pm_critical_path", {"project_id": pid})))
        check("pmo: pm_critical_path", r["critical_count"] > 0, str(r.get("critical_count")))

        r = json.loads(text_of(await client.call_tool("pm_gantt", {"project_id": pid})))
        check("pmo: pm_gantt", len(r["rows"]) == 17, str(len(r.get("rows", []))))

        r = json.loads(text_of(await client.call_tool("pm_add_resource", {
            "name": "Engr. MCP", "role": "site_engineer", "day_rate": 16000})))
        check("pmo: pm_add_resource", r["created"], str(r.get("error")))
        ress = r["resource"]["id"]

        r = json.loads(text_of(await client.call_tool("pm_resources", {})))
        check("pmo: pm_resources", r["count"] >= 1, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("pm_assign", {
            "task_id": STATE["pm_task"], "resource_id": ress, "units_pct": 70})))
        check("pmo: pm_assign", r["created"], str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("pm_resource_load", {"project_id": pid})))
        check("pmo: pm_resource_load", r["count"] >= 1, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("pm_add_cost", {
            "project_id": pid, "amount": 30000000, "category": "structure", "kind": "actual"})))
        check("pmo: pm_add_cost", r["created"], str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("pm_costs", {"project_id": pid})))
        check("pmo: pm_costs", r["count"] == 1 and r["total"] == 30000000.0, str(r["total"]))

        r = json.loads(text_of(await client.call_tool("pm_record_progress", {
            "project_id": pid, "percent": 22.0, "note": "Kick-off", "by": "PM"})))
        check("pmo: pm_record_progress", r["recorded"], str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("pm_progress", {"project_id": pid})))
        check("pmo: pm_progress", 0 < r["actual_pct"] < 100 and "history" in r, str(r["actual_pct"]))

        r = json.loads(text_of(await client.call_tool("pm_earned_value", {"project_id": pid})))
        check("pmo: pm_earned_value", r["EV"] > 0 and r["PV"] > 0 and r["SPI"] is not None,
              str({k: r.get(k) for k in ("EV", "PV", "SPI", "CPI")}))

        r = json.loads(text_of(await client.call_tool("pm_cost_status", {"project_id": pid})))
        check("pmo: pm_cost_status", r["actual_cost"] == 30000000.0
              and r["revised_budget"] == 120000000.0, str(r.get("revised_budget")))

        r = json.loads(text_of(await client.call_tool("pm_s_curve", {"project_id": pid})))
        check("pmo: pm_s_curve", len(r["weeks"]) > 4, str(len(r.get("weeks", []))))

        r = json.loads(text_of(await client.call_tool("pm_health", {"project_id": pid})))
        check("pmo: pm_health", r["overall"] in ("green", "amber", "red")
              and set(r["bands"]) == {"schedule", "cost", "risk", "quality"}, str(r.get("overall")))

        r = json.loads(text_of(await client.call_tool("pm_alerts", {"project_id": pid})))
        check("pmo: pm_alerts", "alerts" in r, str(r.get("count")))

        r = json.loads(text_of(await client.call_tool("pm_kpi", {"project_id": pid})))
        check("pmo: pm_kpi", r["health"] in ("green", "amber", "red"), str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("pm_monitoring", {"project_id": pid})))
        check("pmo: pm_monitoring", r["project"]["id"] == pid and "evm" in r, str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("pm_portfolio", {})))
        check("pmo: pm_portfolio", r["projects"] >= 2 and "by_health" in r, str(r["projects"]))

        r = json.loads(text_of(await client.call_tool("pm_add_risk", {
            "project_id": pid, "title": "Currency risk", "probability": 4, "impact": 4,
            "category": "finance"})))
        check("pmo: pm_add_risk", r["created"] and r["risk"]["band"] == "extreme", str(r["risk"].get("band")))
        risk_id = r["risk"]["id"]

        r = json.loads(text_of(await client.call_tool("pm_risks", {"project_id": pid})))
        check("pmo: pm_risks", r["count"] == 1, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("pm_update_risk", {
            "risk_id": risk_id, "updates": {"status": "mitigating"}})))
        check("pmo: pm_update_risk", r["risk"]["status"] == "mitigating", str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("pm_risk_matrix", {"project_id": pid})))
        check("pmo: pm_risk_matrix", r["count"] == 1 and "cells" in r, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("pm_log_site", {
            "project_id": pid, "work_done": "Excavation", "manpower": 20, "weather": "Clear"})))
        check("pmo: pm_log_site", r["created"], str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("pm_site_logs", {"project_id": pid})))
        check("pmo: pm_site_logs", r["count"] == 1 and r["manpower_total"] == 20, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("pm_site_report", {"project_id": pid})))
        check("pmo: pm_site_report", r["project_id"] == pid and "health" in r, str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("pm_raise_change", {
            "project_id": pid, "title": "Extra basement", "cost_impact": 9000000,
            "schedule_impact_days": 20})))
        check("pmo: pm_raise_change", r["created"], str(r.get("error")))
        change_id = r["change"]["id"]

        r = json.loads(text_of(await client.call_tool("pm_changes", {"project_id": pid})))
        check("pmo: pm_changes", r["count"] == 1, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("pm_decide_change", {
            "change_id": change_id, "approve": True, "by": "Sponsor"})))
        check("pmo: pm_decide_change", r["change"]["status"] == "approved"
              and r["project_budget"] == 129000000.0, str(r.get("project_budget")))

        r = json.loads(text_of(await client.call_tool("pm_add_inspection", {
            "project_id": pid, "title": "Frame inspection", "checklist": [
                {"item": "Concrete grade", "result": "pass"},
                {"item": "Cover", "result": "fail", "note": "missing"}]})))
        check("pmo: pm_add_inspection", r["created"] and r["quality_index"] == 50.0,
              str(r.get("quality_index")))

        r = json.loads(text_of(await client.call_tool("pm_inspections", {"project_id": pid})))
        check("pmo: pm_inspections", r["count"] == 1 and r["quality_index"]["score"] == 50.0,
              str(r["count"]))

        r = json.loads(text_of(await client.call_tool("pm_add_action", {
            "project_id": pid, "title": "Fix cover blocks", "owner": "QA"})))
        check("pmo: pm_add_action", r["created"], str(r.get("error")))
        action_id = r["action"]["id"]

        r = json.loads(text_of(await client.call_tool("pm_actions", {"project_id": pid})))
        check("pmo: pm_actions", r["count"] == 1, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("pm_close_action", {"action_id": action_id})))
        check("pmo: pm_close_action", r["action"]["status"] == "done", str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("pm_project_report", {"project_id": pid})))
        check("pmo: pm_project_report", r["project"]["id"] == pid and "evm" in r and "cost" in r,
              str(r.get("error")))

        html = text_of(await client.call_tool("pm_report_html", {"project_id": pid}))
        check("pmo: pm_report_html", "<html" in html.lower() and len(html) > 4000,
              f"chars={len(html)}")

        html = text_of(await client.call_tool("pm_portal", {"lang": "en"}))
        check("pmo: pm_portal (HTML)", "PMO" in html and "Project register" in html
              and len(html) > 5000, f"chars={len(html)}")

        est = json.loads(text_of(await client.call_tool("tools_overview", {})))
        est_id = core.construction.estimates_db[0].id
        r = json.loads(text_of(await client.call_tool("pm_from_estimate", {
            "estimate_id": est_id, "name": "Imported delivery"})))
        check("pmo: pm_from_estimate", r["created"] and r["project"]["budget"] > 0, str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("pm_apply_template", {"project_id": pid})))
        check("pmo: pm_apply_template", r["tasks_created"] == 0 and r["total_tasks"] >= 16,
              str(r.get("total_tasks")))

        r = json.loads(text_of(await client.call_tool("pm_delete_task", {"task_id": extra_task})))
        check("pmo: pm_delete_task", r["deleted"] is True, str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("portal_settings", {"action": "get"})))
        check("pmo: portal_settings includes pmo", "pmo" in r, str(list(r)[:6]))

        r = json.loads(text_of(await client.call_tool("pm_delete_project", {"project_id": pid})))
        check("pmo: pm_delete_project", r["deleted"] is True, str(r.get("error")))


# ============================================================
# 1g) PMO / project management (REST)
# ============================================================


def run_pmo_rest_checks(client: TestClient) -> None:
    print("\n=== PMO / Project Management (REST) ===")
    with _SharedClient(client):
        r = client.get("/pmo/overview")
        check("GET /pmo/overview", r.status_code == 200 and r.json()["counts"]["projects"] >= 1,
              str(r.status_code))

        r = client.get("/pmo/capabilities")
        check("GET /pmo/capabilities", r.status_code == 200 and r.json()["count"] >= 15,
              str(r.status_code))

        r = client.get("/pmo/project-types")
        check("GET /pmo/project-types", r.status_code == 200 and r.json()["count"] == 8,
              str(r.status_code))

        r = client.get("/pmo/phase-templates", params={"project_type": "construction"})
        check("GET /pmo/phase-templates", r.status_code == 200 and len(r.json()["phases"]) == 9,
              str(r.status_code))

        r = client.post("/pmo/projects", json={"name": "REST Block", "project_type": "construction",
                                               "budget": 80000000, "city": "Karachi",
                                               "start_date": "2026-04-01", "status": "active"})
        check("POST /pmo/projects", r.status_code == 200 and r.json()["created"]
              and r.json()["tasks"] == 16, str(r.status_code))
        pid = r.json()["project"]["id"]

        r = client.get("/pmo/projects")
        check("GET /pmo/projects", r.status_code == 200 and r.json()["count"] >= 2, str(r.status_code))

        r = client.get("/pmo/projects/" + pid)
        check("GET /pmo/projects/{id}", r.status_code == 200 and r.json()["project"]["id"] == pid,
              str(r.status_code))

        r = client.put("/pmo/projects/" + pid, json={"updates": {"priority": "high", "budget": 85000000}})
        check("PUT /pmo/projects/{id}", r.status_code == 200
              and r.json()["updated"]["budget"] == 85000000.0, str(r.status_code))

        r = client.get("/pmo/projects/" + pid + "/dashboard")
        check("GET /pmo/projects/{id}/dashboard", r.status_code == 200 and "evm" in r.json(),
              str(r.status_code))

        r = client.get("/pmo/projects/" + pid + "/report")
        check("GET /pmo/projects/{id}/report", r.status_code == 200 and "schedule" in r.json(),
              str(r.status_code))

        r = client.get("/pmo/projects/" + pid + "/phases")
        check("GET /pmo/projects/{id}/phases", r.status_code == 200 and r.json()["count"] == 9,
              str(r.status_code))

        r = client.post("/pmo/projects/" + pid + "/phases", json={"name": "Custom", "weight": 5})
        check("POST /pmo/projects/{id}/phases", r.status_code == 200 and r.json()["created"],
              str(r.status_code))

        r = client.get("/pmo/projects/" + pid + "/milestones")
        check("GET /pmo/projects/{id}/milestones", r.status_code == 200 and r.json()["count"] == 3,
              str(r.status_code))

        r = client.post("/pmo/projects/" + pid + "/milestones", json={"name": "Piling done",
                                                                     "planned_date": "2026-06-01"})
        check("POST /pmo/projects/{id}/milestones", r.status_code == 200 and r.json()["created"],
              str(r.status_code))

        r = client.get("/pmo/projects/" + pid + "/tasks")
        check("GET /pmo/projects/{id}/tasks", r.status_code == 200 and r.json()["count"] == 16,
              str(r.status_code))
        tid = r.json()["tasks"][0]["id"]

        r = client.post("/pmo/projects/" + pid + "/tasks", json={"name": "Extra task",
                                                                "duration_days": 4})
        check("POST /pmo/projects/{id}/tasks", r.status_code == 200 and r.json()["created"],
              str(r.status_code))
        extra = r.json()["task"]["id"]

        r = client.get("/pmo/tasks/" + tid)
        check("GET /pmo/tasks/{id}", r.status_code == 200 and "planned_start" in r.json(),
              str(r.status_code))

        r = client.put("/pmo/tasks/" + tid, json={"updates": {"progress_pct": 45}})
        check("PUT /pmo/tasks/{id}", r.status_code == 200
              and r.json()["task"]["progress_pct"] == 45.0, str(r.status_code))

        r = client.get("/pmo/projects/" + pid + "/schedule")
        check("GET /pmo/projects/{id}/schedule", r.status_code == 200
              and r.json()["duration_days"] > 100, str(r.status_code))

        r = client.get("/pmo/projects/" + pid + "/critical-path")
        check("GET /pmo/projects/{id}/critical-path", r.status_code == 200
              and r.json()["critical_count"] > 0, str(r.status_code))

        r = client.get("/pmo/projects/" + pid + "/gantt")
        check("GET /pmo/projects/{id}/gantt", r.status_code == 200 and len(r.json()["rows"]) == 17,
              str(r.status_code))

        r = client.post("/pmo/projects/" + pid + "/costs", json={"amount": 12000000,
                                                                "category": "structure"})
        check("POST /pmo/projects/{id}/costs", r.status_code == 200 and r.json()["created"],
              str(r.status_code))

        r = client.get("/pmo/projects/" + pid + "/costs")
        check("GET /pmo/projects/{id}/costs", r.status_code == 200 and r.json()["total"] == 12000000.0,
              str(r.status_code))

        r = client.post("/pmo/projects/" + pid + "/progress", json={"percent": 15, "note": "start"})
        check("POST /pmo/projects/{id}/progress", r.status_code == 200 and r.json()["recorded"],
              str(r.status_code))

        r = client.get("/pmo/projects/" + pid + "/progress")
        check("GET /pmo/projects/{id}/progress", r.status_code == 200 and "history" in r.json(),
              str(r.status_code))

        r = client.get("/pmo/projects/" + pid + "/earned-value")
        check("GET /pmo/projects/{id}/earned-value", r.status_code == 200 and "SPI" in r.json(),
              str(r.status_code))

        r = client.get("/pmo/projects/" + pid + "/cost-status")
        check("GET /pmo/projects/{id}/cost-status", r.status_code == 200
              and r.json()["actual_cost"] == 12000000.0, str(r.status_code))

        r = client.get("/pmo/projects/" + pid + "/s-curve")
        check("GET /pmo/projects/{id}/s-curve", r.status_code == 200 and len(r.json()["weeks"]) > 4,
              str(r.status_code))

        r = client.get("/pmo/projects/" + pid + "/health")
        check("GET /pmo/projects/{id}/health", r.status_code == 200
              and r.json()["overall"] in ("green", "amber", "red"), str(r.status_code))

        r = client.get("/pmo/projects/" + pid + "/kpi")
        check("GET /pmo/projects/{id}/kpi", r.status_code == 200 and "health" in r.json(),
              str(r.status_code))

        r = client.get("/pmo/projects/" + pid + "/monitoring")
        check("GET /pmo/projects/{id}/monitoring", r.status_code == 200 and "evm" in r.json(),
              str(r.status_code))

        r = client.post("/pmo/projects/" + pid + "/risks", json={"title": "REST risk",
                                                                "probability": 3, "impact": 4})
        check("POST /pmo/projects/{id}/risks", r.status_code == 200 and r.json()["created"],
              str(r.status_code))
        risk_id = r.json()["risk"]["id"]

        r = client.get("/pmo/projects/" + pid + "/risks")
        check("GET /pmo/projects/{id}/risks", r.status_code == 200 and r.json()["count"] == 1,
              str(r.status_code))

        r = client.put("/pmo/risks/" + risk_id, json={"updates": {"status": "mitigating"}})
        check("PUT /pmo/risks/{id}", r.status_code == 200
              and r.json()["risk"]["status"] == "mitigating", str(r.status_code))

        r = client.get("/pmo/projects/" + pid + "/risk-matrix")
        check("GET /pmo/projects/{id}/risk-matrix", r.status_code == 200 and "cells" in r.json(),
              str(r.status_code))

        r = client.get("/pmo/risks")
        check("GET /pmo/risks", r.status_code == 200 and r.json()["count"] >= 1, str(r.status_code))

        r = client.post("/pmo/projects/" + pid + "/site-logs", json={"work_done": "Piling",
                                                                    "manpower": 30})
        check("POST /pmo/projects/{id}/site-logs", r.status_code == 200 and r.json()["created"],
              str(r.status_code))

        r = client.get("/pmo/projects/" + pid + "/site-logs")
        check("GET /pmo/projects/{id}/site-logs", r.status_code == 200
              and r.json()["manpower_total"] == 30, str(r.status_code))

        r = client.get("/pmo/projects/" + pid + "/site-report")
        check("GET /pmo/projects/{id}/site-report", r.status_code == 200
              and r.json()["project_id"] == pid, str(r.status_code))

        r = client.post("/pmo/projects/" + pid + "/changes", json={"title": "REST change",
                                                                  "cost_impact": 3000000,
                                                                  "schedule_impact_days": 10})
        check("POST /pmo/projects/{id}/changes", r.status_code == 200 and r.json()["created"],
              str(r.status_code))
        change_id = r.json()["change"]["id"]

        r = client.get("/pmo/projects/" + pid + "/changes")
        check("GET /pmo/projects/{id}/changes", r.status_code == 200 and r.json()["count"] == 1,
              str(r.status_code))

        r = client.post("/pmo/changes/" + change_id + "/decide", json={"approve": True, "by": "Sponsor"})
        check("POST /pmo/changes/{id}/decide", r.status_code == 200
              and r.json()["change"]["status"] == "approved"
              and r.json()["project_budget"] == 88000000.0, str(r.json().get("project_budget")))

        r = client.post("/pmo/projects/" + pid + "/inspections", json={"title": "REST insp",
            "checklist": [{"item": "a", "result": "pass"}, {"item": "b", "result": "pass"}]})
        check("POST /pmo/projects/{id}/inspections", r.status_code == 200
              and r.json()["quality_index"] == 100.0, str(r.status_code))

        r = client.get("/pmo/projects/" + pid + "/inspections")
        check("GET /pmo/projects/{id}/inspections", r.status_code == 200
              and r.json()["count"] == 1, str(r.status_code))

        r = client.post("/pmo/projects/" + pid + "/actions", json={"title": "REST action",
                                                                  "owner": "QA"})
        check("POST /pmo/projects/{id}/actions", r.status_code == 200 and r.json()["created"],
              str(r.status_code))
        action_id = r.json()["action"]["id"]

        r = client.get("/pmo/projects/" + pid + "/actions")
        check("GET /pmo/projects/{id}/actions", r.status_code == 200 and r.json()["count"] == 1,
              str(r.status_code))

        r = client.post("/pmo/actions/" + action_id + "/close")
        check("POST /pmo/actions/{id}/close", r.status_code == 200
              and r.json()["action"]["status"] == "done", str(r.status_code))

        r = client.get("/pmo/actions")
        check("GET /pmo/actions", r.status_code == 200 and r.json()["count"] >= 1, str(r.status_code))

        r = client.post("/pmo/resources", json={"name": "REST resource", "role": "foreman"})
        check("POST /pmo/resources", r.status_code == 200 and r.json()["created"], str(r.status_code))
        res_id = r.json()["resource"]["id"]

        r = client.get("/pmo/resources")
        check("GET /pmo/resources", r.status_code == 200 and r.json()["count"] >= 1, str(r.status_code))

        r = client.post("/pmo/allocations", json={"task_id": tid, "resource_id": res_id,
                                                  "units_pct": 50})
        check("POST /pmo/allocations", r.status_code == 200 and r.json()["created"], str(r.status_code))

        r = client.get("/pmo/resource-load", params={"project_id": pid})
        check("GET /pmo/resource-load", r.status_code == 200 and r.json()["count"] >= 1,
              str(r.status_code))

        r = client.get("/pmo/alerts", params={"project_id": pid})
        check("GET /pmo/alerts", r.status_code == 200 and "alerts" in r.json(), str(r.status_code))

        r = client.get("/pmo/portfolio")
        check("GET /pmo/portfolio", r.status_code == 200 and r.json()["projects"] >= 2,
              str(r.status_code))

        est_id = core.construction.estimates_db[0].id
        r = client.post("/pmo/from-estimate/" + est_id, params={"name": "REST import"})
        check("POST /pmo/from-estimate/{id}", r.status_code == 200 and r.json()["created"],
              str(r.status_code))

        r = client.post("/pmo/projects/" + pid + "/apply-template")
        check("POST /pmo/projects/{id}/apply-template", r.status_code == 200
              and r.json()["tasks_created"] == 0 and r.json()["total_tasks"] >= 16,
              str(r.status_code))

        r = client.delete("/pmo/tasks/" + extra)
        check("DELETE /pmo/tasks/{id}", r.status_code == 200 and r.json()["deleted"] is True,
              str(r.status_code))

        r = client.get("/pmo/portal")
        check("GET /pmo/portal (HTML)", r.status_code == 200 and "PMO" in r.text
              and "Project register" in r.text, str(r.status_code))

        r = client.get("/pmo/portal.html", params={"lang": "ur", "theme": "dark"})
        check("GET /pmo/portal.html (ur/dark)", r.status_code == 200 and 'dir="rtl"' in r.text,
              str(r.status_code))

        r = client.get("/pmo/report.html", params={"project_id": pid})
        check("GET /pmo/report.html", r.status_code == 200 and "<html" in r.text.lower(),
              str(r.status_code))

        r = client.delete("/pmo/projects/" + pid)
        check("DELETE /pmo/projects/{id}", r.status_code == 200 and r.json()["deleted"] is True,
              str(r.status_code))


# ============================================================
# 1f) Team messaging & notifications (MCP)
# ============================================================


async def run_messaging_checks() -> None:
    print("\n=== Team Messaging & Notifications (MCP) ===")
    async with Client(core.mcp) as client:
        r = json.loads(text_of(await client.call_tool("msg_overview", {})))
        check("msg: msg_overview", r["counts"]["conversations"] >= 6,
              str(r["counts"]["conversations"]))
        check("msg: msg_overview rollout", len(r["rollout"]) == 4, str(r["rollout"]))

        r = json.loads(text_of(await client.call_tool("msg_channels", {})))
        check("msg: msg_channels", r["count"] == 6 and any(c["key"] == "management" and c["restricted"]
                                                          for c in r["channels"]), str(r["count"]))
        r = json.loads(text_of(await client.call_tool("msg_channels", {"channel_key": "gis_mapping"})))
        check("msg: msg_channels(key)", r["channel"]["name"] == "GIS & Mapping", str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("msg_categories", {})))
        check("msg: msg_categories", r["count"] == 8, str(r["count"]))
        r = json.loads(text_of(await client.call_tool("msg_categories", {"category": "mention"})))
        check("msg: msg_categories(mention)", "telegram" in r["category"]["channels"], str(r))

        r = json.loads(text_of(await client.call_tool("msg_attachment_kinds", {})))
        check("msg: msg_attachment_kinds", r["count"] == 9, str(r["count"]))

        profs = json.loads(text_of(await client.call_tool("msg_profiles", {})))
        check("msg: msg_profiles", profs["count"] >= 3, str(profs["count"]))
        admin_prof = next((p for p in profs["profiles"] if p["role"] in core.messaging.ADMIN_ROLES),
                          profs["profiles"][0])
        uid = admin_prof["user_id"]
        uid2 = next(p["user_id"] for p in profs["profiles"] if p["user_id"] != uid)

        r = json.loads(text_of(await client.call_tool("msg_set_presence",
                                                      {"user_id": uid, "presence": "online"})))
        check("msg: msg_set_presence", r["presence"] == "online", str(r.get("error")))
        r = json.loads(text_of(await client.call_tool("msg_presence_heartbeat", {"user_id": uid})))
        check("msg: msg_presence_heartbeat", r.get("presence") in ("online", "away", "busy"),
              str(r.get("error")))

        prefs = json.loads(text_of(await client.call_tool("msg_preferences", {"user_id": uid})))
        check("msg: msg_preferences", "mention" in prefs["notification_prefs"], str(prefs.get("error")))
        r = json.loads(text_of(await client.call_tool("msg_set_preferences", {
            "user_id": uid, "prefs": {"lead": ["in_app"]}, "digest": "hourly"})))
        check("msg: msg_set_preferences", r["notification_prefs"]["lead"] == ["in_app"]
              and r["digest"] == "hourly", str(r.get("error")))

        # --- conversations ---
        dm = json.loads(text_of(await client.call_tool("msg_direct", {"user_a": uid, "user_b": uid2})))
        check("msg: msg_direct", dm["conversation"]["kind"] == "direct", str(dm.get("error")))
        dm_id = dm["conversation"]["id"]

        r = json.loads(text_of(await client.call_tool("msg_create_conversation", {
            "kind": "group", "title": "MCP test group", "created_by": uid,
            "participants": [uid, uid2]})))
        group_id = r["conversation"]["id"]
        check("msg: msg_create_conversation", r["conversation"]["member_count"] == 2, str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("msg_conversations", {"user_id": uid})))
        check("msg: msg_conversations", r["count"] >= 2, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("msg_conversation", {"conversation_id": group_id,
                                                                          "user_id": uid})))
        check("msg: msg_conversation", r["conversation"]["title"] == "MCP test group", str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("msg_conversation_context",
                                                      {"conversation_id": group_id})))
        check("msg: msg_conversation_context", "attachments" in r, str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("msg_add_member", {
            "conversation_id": group_id, "member_id": "mcp_guest", "actor_id": uid, "role": "guest"})))
        check("msg: msg_add_member", r["created"] is True, str(r.get("error")))
        r = json.loads(text_of(await client.call_tool("msg_members", {"conversation_id": group_id})))
        check("msg: msg_members", r["count"] == 3, str(r["count"]))
        r = json.loads(text_of(await client.call_tool("msg_update_member", {
            "conversation_id": group_id, "member_id": "mcp_guest", "actor_id": uid, "role": "member"})))
        check("msg: msg_update_member", r["member"]["role"] == "member", str(r.get("error")))
        r = json.loads(text_of(await client.call_tool("msg_remove_member", {
            "conversation_id": group_id, "member_id": "mcp_guest", "actor_id": uid,
            "reason": "test"})))
        check("msg: msg_remove_member", r["removed"] is True, str(r.get("error")))

        # --- messages ---
        r = json.loads(text_of(await client.call_tool("msg_post", {
            "conversation_id": dm_id, "author_id": uid,
            "body": "MCP hello - please confirm the rate list.", "mentions": [uid2]})))
        check("msg: msg_post", r["message"]["mentions"] == [uid2], str(r.get("error")))
        mid = r["message"]["id"]

        r = json.loads(text_of(await client.call_tool("msg_messages", {
            "conversation_id": dm_id, "user_id": uid, "limit": 10})))
        check("msg: msg_messages", r["count"] >= 1, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("msg_message", {"message_id": mid, "user_id": uid})))
        check("msg: msg_message", r["message"]["id"] == mid, str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("msg_search", {"user_id": uid, "query": "rate list"})))
        check("msg: msg_search", r["count"] >= 1, str(r["count"]))
        r = json.loads(text_of(await client.call_tool("msg_search", {"user_id": uid2, "mention": uid2})))
        check("msg: msg_search(mention)", r["count"] >= 1, str(r["count"]))

        r = json.loads(text_of(await client.call_tool("msg_react", {
            "message_id": mid, "user_id": uid2, "emoji": "ok"})))
        check("msg: msg_react", "ok" in r["reactions"], str(r.get("error")))
        r = json.loads(text_of(await client.call_tool("msg_pin_message", {
            "message_id": mid, "user_id": uid})))
        check("msg: msg_pin_message", r["pinned"] is True, str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("msg_edit_message", {
            "message_id": mid, "user_id": uid, "body": "MCP hello - please confirm the rate list today."})))
        check("msg: msg_edit_message", r["message"]["edited_at"] is not None, str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("msg_thread", {"message_id": mid, "user_id": uid})))
        check("msg: msg_thread", r["count"] == 0, str(r["count"]))
        r = json.loads(text_of(await client.call_tool("msg_read_receipts",
                                                      {"message_id": mid, "user_id": uid})))
        check("msg: msg_read_receipts", r["of"] == 1, str(r))

        r = json.loads(text_of(await client.call_tool("msg_mark_read", {"conversation_id": dm_id,
                                                                       "user_id": uid2})))
        check("msg: msg_mark_read", "last_read_seq" in r, str(r.get("error")))
        r = json.loads(text_of(await client.call_tool("msg_unread", {"user_id": uid2})))
        dm_unread = [c for c in r["conversations"] if c["conversation_id"] == dm_id]
        check("msg: msg_unread", not dm_unread, str(dm_unread))

        r = json.loads(text_of(await client.call_tool("msg_summarize", {"conversation_id": dm_id,
                                                                       "user_id": uid})))
        check("msg: msg_summarize", r["window"] >= 1 and "topics" in r, str(r.get("error")))
        r = json.loads(text_of(await client.call_tool("msg_action_items", {"conversation_id": dm_id,
                                                                          "user_id": uid})))
        check("msg: msg_action_items", r["suggestions"] >= 1, str(r.get("suggestions")))
        r = json.loads(text_of(await client.call_tool("msg_conversation_digest", {
            "conversation_id": dm_id, "user_id": uid, "days": 30})))
        check("msg: msg_conversation_digest", r["messages"] >= 1, str(r.get("error")))

        # --- attachments & expiring links ---
        r = json.loads(text_of(await client.call_tool("msg_attach", {
            "conversation_id": dm_id, "uploaded_by": uid, "filename": "site-plan.pdf",
            "size_bytes": 4096})))
        att_id = r["attachment"]["id"]
        check("msg: msg_attach", r["attachment"]["sensitivity"] == "confidential", str(r.get("error")))
        r = json.loads(text_of(await client.call_tool("msg_attachments", {
            "conversation_id": dm_id, "user_id": uid})))
        check("msg: msg_attachments", r["count"] == 1, str(r["count"]))
        r = json.loads(text_of(await client.call_tool("msg_attachment_link", {
            "attachment_id": att_id, "user_id": uid, "ttl_minutes": 5})))
        token = r["token"]
        check("msg: msg_attachment_link", r["expires_at"] and r["url"].startswith("/messaging/attachments/"),
              str(r.get("error")))
        r = json.loads(text_of(await client.call_tool("msg_attachment_resolve", {"token": token,
                                                                               "user_id": uid})))
        check("msg: msg_attachment_resolve", r["valid"] is True, str(r.get("error")))
        r = json.loads(text_of(await client.call_tool("msg_attachment_resolve", {"token": token + "0",
                                                                               "user_id": uid})))
        check("msg: msg_attachment_resolve(bad)", r["valid"] is False, str(r))

        # --- actions ---
        r = json.loads(text_of(await client.call_tool("msg_create_action", {
            "conversation_id": dm_id, "created_by": uid, "title": "Verify title deed",
            "kind": "verification", "message_id": mid, "owner_id": uid2, "due_on": "2020-01-01",
            "create_crm_task": True})))
        act_id = r["action"]["id"]
        check("msg: msg_create_action", r["action"]["kind"] == "verification", str(r.get("error")))
        check("msg: msg_create_action crm", r["action"]["linked_task_id"] is not None, str(r["action"]))
        r = json.loads(text_of(await client.call_tool("msg_action", {"action_id": act_id, "user_id": uid})))
        check("msg: msg_action", r["action"]["overdue"] is True, str(r.get("error")))
        r = json.loads(text_of(await client.call_tool("msg_actions", {"user_id": uid,
                                                                     "overdue_only": True})))
        check("msg: msg_actions", r["count"] >= 1 and r["overdue"] >= 1, str(r["count"]))
        r = json.loads(text_of(await client.call_tool("msg_update_action", {
            "action_id": act_id, "user_id": uid2, "note": "started"})))
        check("msg: msg_update_action", len(r["action"]["updates"]) == 1, str(r.get("error")))
        r = json.loads(text_of(await client.call_tool("msg_complete_action", {
            "action_id": act_id, "user_id": uid2})))
        check("msg: msg_complete_action", r["action"]["status"] == "done", str(r.get("error")))

        # --- notifications, outbox, dispatch ---
        r = json.loads(text_of(await client.call_tool("msg_notifications", {"user_id": uid2})))
        check("msg: msg_notifications", r["count"] >= 1, str(r["count"]))
        nid = r["notifications"][0]["id"]
        r = json.loads(text_of(await client.call_tool("msg_read_notification", {
            "notification_id": nid, "user_id": uid2})))
        check("msg: msg_read_notification", r["notification"]["status"] == "read", str(r.get("error")))
        r = json.loads(text_of(await client.call_tool("msg_dispatch", {"force": True})))
        check("msg: msg_dispatch", r["scanned"] >= 0, str(r.get("error")))
        r = json.loads(text_of(await client.call_tool("msg_outbox", {})))
        check("msg: msg_outbox", r["count"] >= 1 and "email" in r["by_channel"], str(r["by_channel"]))
        r = json.loads(text_of(await client.call_tool("msg_mark_all_notifications_read",
                                                      {"user_id": uid2})))
        check("msg: msg_mark_all_notifications_read", "marked_read" in r, str(r.get("error")))
        r = json.loads(text_of(await client.call_tool("msg_unread_summary", {"user_id": uid2})))
        check("msg: msg_unread_summary", "notifications_unread" in r and "open_actions" in r, str(r))

        # --- telegram ---
        r = json.loads(text_of(await client.call_tool("msg_telegram_link_code", {"user_id": uid2})))
        code = r["code"]
        check("msg: msg_telegram_link_code", len(code) >= 4, str(r.get("error")))
        r = json.loads(text_of(await client.call_tool("msg_telegram_update", {
            "update": {"message": {"chat": {"id": "777", "username": "mcp"}, "text": f"/start {code}"}}})))
        check("msg: msg_telegram_update /start", r["action"] == "linked", str(r))
        r = json.loads(text_of(await client.call_tool("msg_telegram_status", {"user_id": uid2})))
        check("msg: msg_telegram_status", r["linked"] is True, str(r.get("error")))
        r = json.loads(text_of(await client.call_tool("msg_telegram_update", {
            "update": {"message": {"chat": {"id": "777"}, "text": "/digest"}}})))
        check("msg: msg_telegram_update /digest", r["action"] == "digest", str(r))
        r = json.loads(text_of(await client.call_tool("msg_telegram_alert", {
            "user_id": uid2, "text": "A GIS processing job has completed.", "priority": "high"})))
        check("msg: msg_telegram_alert", r["dispatched"] >= 1 and r["telegram_item"]["channel"] == "telegram",
              str(r.get("error")))
        r = json.loads(text_of(await client.call_tool("msg_telegram_links", {})))
        check("msg: msg_telegram_links", r["count"] >= 1, str(r["count"]))
        r = json.loads(text_of(await client.call_tool("msg_telegram_unlink", {"user_id": uid2})))
        check("msg: msg_telegram_unlink", r["unlinked"] is True, str(r.get("error")))

        # --- audit, retention, moderation, stats, portals ---
        r = json.loads(text_of(await client.call_tool("msg_audit", {"limit": 20})))
        check("msg: msg_audit", r["count"] >= 1 and r["actions"], str(r["count"]))
        r = json.loads(text_of(await client.call_tool("msg_retention_report", {})))
        check("msg: msg_retention_report", "conversations" in r and r["default_retention_days"] > 0, str(r.get("error")))
        r = json.loads(text_of(await client.call_tool("msg_purge_retention", {"dry_run": True})))
        check("msg: msg_purge_retention", r["dry_run"] is True and r["purged"] == 0, str(r))

        r = json.loads(text_of(await client.call_tool("msg_report_message", {
            "message_id": mid, "reporter_id": uid2, "reason": "off_topic"})))
        rep_id = r["report"]["id"]
        check("msg: msg_report_message", r["report"]["status"] == "open", str(r.get("error")))
        r = json.loads(text_of(await client.call_tool("msg_reports", {})))
        check("msg: msg_reports", r["count"] >= 1, str(r["count"]))
        r = json.loads(text_of(await client.call_tool("msg_moderate_report", {
            "report_id": rep_id, "actor_id": uid, "action": "dismiss"})))
        check("msg: msg_moderate_report", r["report"]["status"] == "dismissed", str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("msg_statistics", {})))
        check("msg: msg_statistics", r["conversations"] >= 6 and r["messages_live"] >= 1,
              str(r["conversations"]))

        r = json.loads(text_of(await client.call_tool("msg_delete_message", {
            "message_id": mid, "user_id": uid, "reason": "cleanup"})))
        check("msg: msg_delete_message", r["deleted"] is True, str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("msg_property_thread", {
            "property_id": core.properties_db[0].id, "created_by": uid})))
        check("msg: msg_property_thread", r["conversation"]["kind"] == "property", str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("msg_create_conversation", {
            "kind": "channel", "channel_key": "management", "created_by": uid,
            "participants": [uid]})))
        mgt_id = r["conversation"]["id"]
        check("msg: management channel restricted", r["conversation"]["restricted"] is True,
              str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("msg_revoke_access", {
            "user_id": uid2, "actor_id": uid, "reason": "left company"})))
        check("msg: msg_revoke_access", r["conversations_revoked"] >= 1, str(r.get("error")))

        r = json.loads(text_of(await client.call_tool("msg_archive_conversation", {
            "conversation_id": group_id, "user_id": uid, "archived": True})))
        check("msg: msg_archive_conversation", r["status"] == "archived", str(r.get("error")))
        check("msg: management id", mgt_id.startswith("cnv_"), mgt_id)

        r = text_of(await client.call_tool("msg_portal", {}))
        check("msg: msg_portal", "<html" in r.lower() and "Messaging" in r, r[:80])


def run_messaging_rest_checks(client: TestClient) -> None:
    print("\n=== Team Messaging & Notifications (REST) ===")
    with _SharedClient(client):
        r = client.get("/messaging/overview")
        check("GET /messaging/overview", r.status_code == 200 and r.json()["counts"]["conversations"] >= 1,
              str(r.status_code))

        r = client.get("/messaging/channels")
        check("GET /messaging/channels", r.status_code == 200 and r.json()["count"] == 6,
              str(r.status_code))
        r = client.get("/messaging/channels/sales")
        check("GET /messaging/channels/sales", r.status_code == 200
              and r.json()["channel"]["name"] == "Sales", str(r.status_code))
        r = client.get("/messaging/categories")
        check("GET /messaging/categories", r.status_code == 200 and r.json()["count"] == 8,
              str(r.status_code))
        r = client.get("/messaging/attachment-kinds")
        check("GET /messaging/attachment-kinds", r.status_code == 200 and r.json()["count"] == 9,
              str(r.status_code))
        r = client.get("/messaging/profiles")
        check("GET /messaging/profiles", r.status_code == 200 and r.json()["count"] >= 3,
              str(r.status_code))

        r = client.post("/messaging/presence", json={"user_id": "rest_u1", "presence": "online"})
        check("POST /messaging/presence", r.status_code == 200 and r.json()["presence"] == "online",
              str(r.status_code))
        r = client.post("/messaging/presence/heartbeat", json={"user_id": "rest_u1"})
        check("POST /messaging/presence/heartbeat", r.status_code == 200, str(r.status_code))

        r = client.get("/messaging/preferences/rest_u1")
        check("GET /messaging/preferences/{id}", r.status_code == 200
              and "notification_prefs" in r.json(), str(r.status_code))
        r = client.put("/messaging/preferences/rest_u1", json={"prefs": {"task": ["in_app"]}, "digest": "daily"})
        check("PUT /messaging/preferences/{id}", r.status_code == 200
              and r.json()["notification_prefs"]["task"] == ["in_app"], str(r.status_code))

        r = client.post("/messaging/direct", json={"user_a": "rest_u1", "user_b": "rest_u2"})
        check("POST /messaging/direct", r.status_code == 200
              and r.json()["conversation"]["kind"] == "direct", str(r.status_code))
        dm_id = r.json()["conversation"]["id"]

        r = client.post("/messaging/conversations", json={
            "kind": "group", "title": "REST group", "created_by": "rest_u1",
            "participants": ["rest_u1", "rest_u2"]})
        check("POST /messaging/conversations", r.status_code == 201
              and r.json()["conversation"]["member_count"] == 2, str(r.status_code))
        group_id = r.json()["conversation"]["id"]

        r = client.get("/messaging/conversations", params={"user_id": "rest_u1"})
        check("GET /messaging/conversations", r.status_code == 200 and r.json()["count"] >= 2,
              str(r.status_code))
        r = client.get("/messaging/conversations/" + group_id, params={"user_id": "rest_u1"})
        check("GET /messaging/conversations/{id}", r.status_code == 200
              and r.json()["conversation"]["id"] == group_id, str(r.status_code))
        r = client.get("/messaging/conversations/" + group_id + "/context")
        check("GET /messaging/conversations/{id}/context", r.status_code == 200
              and "attachments" in r.json(), str(r.status_code))

        r = client.post("/messaging/conversations/" + group_id + "/members",
                        json={"member_id": "rest_u3", "actor_id": "rest_u1", "role": "member"})
        check("POST .../members", r.status_code == 200 and r.json()["created"] is True,
              str(r.status_code))
        r = client.get("/messaging/conversations/" + group_id + "/members")
        check("GET .../members", r.status_code == 200 and r.json()["count"] == 3, str(r.status_code))
        r = client.put("/messaging/conversations/" + group_id + "/members/rest_u3",
                       json={"actor_id": "rest_u1", "role": "guest"})
        check("PUT .../members/{id}", r.status_code == 200
              and r.json()["member"]["role"] == "guest", str(r.status_code))
        r = client.delete("/messaging/conversations/" + group_id + "/members/rest_u3",
                          params={"actor_id": "rest_u1", "reason": "test"})
        check("DELETE .../members/{id}", r.status_code == 200 and r.json()["removed"] is True,
              str(r.status_code))

        prop_id = core.properties_db[0].id
        r = client.post("/messaging/property-thread", json={"property_id": prop_id,
                                                            "created_by": "rest_u1"})
        check("POST /messaging/property-thread", r.status_code == 200
              and r.json()["conversation"]["kind"] == "property", str(r.status_code))

        r = client.post("/messaging/conversations/" + dm_id + "/messages",
                        json={"author_id": "rest_u1", "body": "REST hello, please confirm.",
                              "mentions": ["rest_u2"]})
        check("POST .../messages", r.status_code == 201
              and r.json()["message"]["mentions"] == ["rest_u2"], str(r.status_code))
        mid = r.json()["message"]["id"]

        r = client.get("/messaging/conversations/" + dm_id + "/messages",
                       params={"user_id": "rest_u1"})
        check("GET .../messages", r.status_code == 200 and r.json()["count"] >= 1, str(r.status_code))
        r = client.get("/messaging/messages/" + mid, params={"user_id": "rest_u1"})
        check("GET /messaging/messages/{id}", r.status_code == 200
              and r.json()["message"]["id"] == mid, str(r.status_code))
        r = client.put("/messaging/messages/" + mid,
                       json={"user_id": "rest_u1", "body": "REST hello, please confirm today."})
        check("PUT /messaging/messages/{id}", r.status_code == 200
              and r.json()["message"]["edited_at"], str(r.status_code))
        r = client.post("/messaging/messages/" + mid + "/react",
                        json={"user_id": "rest_u2", "emoji": "ok"})
        check("POST .../react", r.status_code == 200 and "ok" in r.json()["reactions"],
              str(r.status_code))
        r = client.post("/messaging/messages/" + mid + "/pin", json={"user_id": "rest_u1"})
        check("POST .../pin", r.status_code == 200 and r.json()["pinned"] is True, str(r.status_code))
        r = client.get("/messaging/messages/" + mid + "/thread", params={"user_id": "rest_u1"})
        check("GET .../thread", r.status_code == 200 and r.json()["count"] == 0, str(r.status_code))
        r = client.get("/messaging/messages/" + mid + "/receipts", params={"user_id": "rest_u1"})
        check("GET .../receipts", r.status_code == 200 and r.json()["of"] == 1, str(r.status_code))

        r = client.get("/messaging/search", params={"user_id": "rest_u1", "query": "hello"})
        check("GET /messaging/search", r.status_code == 200 and r.json()["count"] >= 1,
              str(r.status_code))
        r = client.post("/messaging/conversations/" + dm_id + "/read",
                        json={"user_id": "rest_u2"})
        check("POST .../read", r.status_code == 200 and "last_read_seq" in r.json(), str(r.status_code))
        r = client.get("/messaging/unread/rest_u2")
        check("GET /messaging/unread/{id}", r.status_code == 200 and r.json()["total"] == 0,
              str(r.status_code))
        r = client.get("/messaging/conversations/" + dm_id + "/summary",
                       params={"user_id": "rest_u1"})
        check("GET .../summary", r.status_code == 200 and "topics" in r.json(), str(r.status_code))
        r = client.get("/messaging/conversations/" + dm_id + "/digest",
                       params={"user_id": "rest_u1"})
        check("GET .../digest", r.status_code == 200 and r.json()["messages"] >= 1, str(r.status_code))
        r = client.post("/messaging/conversations/" + dm_id + "/action-items",
                        json={"user_id": "rest_u1"})
        check("POST .../action-items", r.status_code == 200 and r.json()["suggestions"] >= 1,
              str(r.status_code))

        r = client.post("/messaging/conversations/" + dm_id + "/attachments",
                        json={"uploaded_by": "rest_u1", "filename": "deed.pdf", "size_bytes": 2048})
        check("POST .../attachments", r.status_code == 201
              and r.json()["attachment"]["kind"] == "pdf", str(r.status_code))
        att_id = r.json()["attachment"]["id"]
        r = client.get("/messaging/conversations/" + dm_id + "/attachments",
                       params={"user_id": "rest_u1"})
        check("GET .../attachments", r.status_code == 200 and r.json()["count"] == 1, str(r.status_code))
        r = client.get("/messaging/attachments/" + att_id + "/link", params={"user_id": "rest_u1"})
        check("GET .../link", r.status_code == 200 and "token" in r.json(), str(r.status_code))
        token = r.json()["token"]
        r = client.get("/messaging/attachments/" + att_id, params={"token": token, "user_id": "rest_u1"})
        check("GET /messaging/attachments/{id}", r.status_code == 200 and r.json()["valid"] is True,
              str(r.status_code))
        r = client.get("/messaging/attachments/" + att_id)
        check("GET /messaging/attachments/{id} (no token)", r.status_code == 400, str(r.status_code))
        r = client.get("/messaging/attachments/resolve/" + token, params={"user_id": "rest_u1"})
        check("GET /messaging/attachments/resolve/{token}", r.status_code == 200
              and r.json()["valid"] is True, str(r.status_code))

        r = client.post("/messaging/conversations/" + dm_id + "/actions", json={
            "created_by": "rest_u1", "title": "Verify deed", "owner_id": "rest_u2",
            "due_on": "2020-01-01", "create_crm_task": True})
        check("POST .../actions", r.status_code == 201
              and r.json()["action"]["linked_task_id"], str(r.status_code))
        act_id = r.json()["action"]["id"]
        r = client.get("/messaging/actions/" + act_id, params={"user_id": "rest_u1"})
        check("GET /messaging/actions/{id}", r.status_code == 200
              and r.json()["action"]["overdue"] is True, str(r.status_code))
        r = client.get("/messaging/actions", params={"user_id": "rest_u1", "overdue_only": True})
        check("GET /messaging/actions", r.status_code == 200 and r.json()["count"] >= 1,
              str(r.status_code))
        r = client.put("/messaging/actions/" + act_id, json={"user_id": "rest_u2", "note": "started"})
        check("PUT /messaging/actions/{id}", r.status_code == 200, str(r.status_code))
        r = client.post("/messaging/actions/" + act_id + "/complete", json={"user_id": "rest_u2"})
        check("POST /messaging/actions/{id}/complete", r.status_code == 200
              and r.json()["action"]["status"] == "done", str(r.status_code))

        r = client.post("/messaging/dispatch", json={"force": True})
        check("POST /messaging/dispatch", r.status_code == 200, str(r.status_code))
        r = client.get("/messaging/notifications/rest_u2")
        check("GET /messaging/notifications/{id}", r.status_code == 200 and r.json()["count"] >= 1,
              str(r.status_code))
        nid = r.json()["notifications"][0]["id"]
        r = client.post("/messaging/notifications/" + nid + "/read", params={"user_id": "rest_u2"})
        check("POST .../notifications/{id}/read", r.status_code == 200
              and r.json()["notification"]["status"] == "read", str(r.status_code))
        r = client.post("/messaging/notifications/rest_u2/read-all")
        check("POST .../read-all", r.status_code == 200 and "marked_read" in r.json(), str(r.status_code))
        r = client.get("/messaging/outbox")
        check("GET /messaging/outbox", r.status_code == 200 and r.json()["count"] >= 1,
              str(r.status_code))
        r = client.get("/messaging/unread-summary/rest_u2")
        check("GET /messaging/unread-summary/{id}", r.status_code == 200
              and "open_actions" in r.json(), str(r.status_code))

        r = client.post("/messaging/telegram/link-code", params={"user_id": "rest_u2"})
        check("POST /messaging/telegram/link-code", r.status_code == 200 and r.json()["code"],
              str(r.status_code))
        code = r.json()["code"]
        r = client.post("/messaging/telegram/update", json={"update": {"message": {
            "chat": {"id": "42", "username": "rest"}, "text": "/start " + code}}})
        check("POST /messaging/telegram/update", r.status_code == 200
              and r.json()["action"] == "linked", str(r.status_code))
        r = client.get("/messaging/telegram/status/rest_u2")
        check("GET /messaging/telegram/status/{id}", r.status_code == 200
              and r.json()["linked"] is True, str(r.status_code))
        r = client.get("/messaging/telegram/links")
        check("GET /messaging/telegram/links", r.status_code == 200 and r.json()["count"] >= 1,
              str(r.status_code))
        r = client.post("/messaging/telegram/alert", json={"user_id": "rest_u2",
                                                           "text": "Your report is ready.",
                                                           "priority": "high"})
        check("POST /messaging/telegram/alert", r.status_code == 200
              and r.json()["telegram_item"]["channel"] == "telegram", str(r.status_code))
        r = client.post("/messaging/telegram/unlink", params={"user_id": "rest_u2"})
        check("POST /messaging/telegram/unlink", r.status_code == 200
              and r.json()["unlinked"] is True, str(r.status_code))

        r = client.get("/messaging/audit")
        check("GET /messaging/audit", r.status_code == 200 and r.json()["count"] >= 1, str(r.status_code))
        r = client.get("/messaging/retention")
        check("GET /messaging/retention", r.status_code == 200 and "conversations" in r.json(),
              str(r.status_code))
        r = client.post("/messaging/purge", json={"dry_run": True})
        check("POST /messaging/purge", r.status_code == 200 and r.json()["purged"] == 0, str(r.status_code))
        r = client.post("/messaging/reports", json={"message_id": mid, "reporter_id": "rest_u2",
                                                    "reason": "off_topic"})
        check("POST /messaging/reports", r.status_code == 201 and r.json()["report"]["status"] == "open",
              str(r.status_code))
        rep_id = r.json()["report"]["id"]
        r = client.get("/messaging/reports")
        check("GET /messaging/reports", r.status_code == 200 and r.json()["count"] >= 1,
              str(r.status_code))
        r = client.post("/messaging/reports/" + rep_id + "/moderate",
                        json={"actor_id": "rest_u1", "action": "dismiss"})
        check("POST .../moderate", r.status_code == 200
              and r.json()["report"]["status"] == "dismissed", str(r.status_code))
        r = client.get("/messaging/statistics")
        check("GET /messaging/statistics", r.status_code == 200 and r.json()["conversations"] >= 1,
              str(r.status_code))

        r = client.get("/messaging/portal")
        check("GET /messaging/portal", r.status_code == 200 and "Messaging" in r.text, str(r.status_code))
        r = client.get("/messaging/portal.html", params={"lang": "ur", "theme": "dark"})
        check("GET /messaging/portal.html (ur/dark)", r.status_code == 200 and 'dir="rtl"' in r.text,
              str(r.status_code))

        # --- real-time feed ---
        try:
            with client.websocket_connect(f"/ws/messaging/{dm_id}?user_id=rest_u1&token={STATE['admin_token']}") as ws:
                ready = ws.receive_json()
                check("WS /ws/messaging/{id} (ready)", ready["event"] == "ready", str(ready))
                ws.send_text("unread")
                nxt = ws.receive_json()
                check("WS /ws/messaging/{id} (unread)",
                      nxt["event"] in ("unread", "message.created", "message.updated"), str(nxt))
        except Exception as exc:  # pragma: no cover - transport failures
            check("WS /ws/messaging/{id} (ready)", False, repr(exc))
        try:
            with client.websocket_connect(f"/ws/messaging/{dm_id}?user_id=nobody&token={STATE['admin_token']}") as ws:
                ws.receive_json()
            check("WS /ws/messaging/{id} (denied)", False, "expected close")
        except Exception:
            check("WS /ws/messaging/{id} (denied)", True)
        try:
            with client.websocket_connect(f"/ws/messaging/{dm_id}?user_id=rest_u1") as ws:
                ws.receive_json()
            check("WS /ws/messaging/{id} (no token -> refused)", False, "expected close")
        except Exception:
            check("WS /ws/messaging/{id} (no token -> refused)", True)

        r = client.post("/messaging/revoke-access", json={"user_id": "rest_u2",
                                                          "actor_id": "rest_u1",
                                                          "reason": "left company"})
        check("POST /messaging/revoke-access", r.status_code == 200
              and r.json()["conversations_revoked"] >= 1, str(r.status_code))


# ============================================================
# main
# ============================================================


async def main() -> int:
    mcp_lead_id, mcp_layer_id = await run_mcp_checks()
    await run_wing_checks()
    await run_products_checks()
    await run_tools_checks()
    await run_pmo_checks()
    await run_messaging_checks()
    run_fastapi_checks(mcp_lead_id, mcp_layer_id)

    print("\n=== Summary ===")
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    for name, ok, detail in RESULTS:
        mark = "PASS" if ok else "FAIL"
        line = f"  [{mark}] {name}"
        if not ok and detail:
            line += f"  ->  {detail}"
        print(line)
    print(f"\n{passed}/{len(RESULTS)} checks passed")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
