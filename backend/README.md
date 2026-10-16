# Real Estate Portal — Backend

A hierarchical Pakistani real-estate portal exposed over **two protocols that share
one data store**:

* **MCP** (Model Context Protocol) — tools, resources and prompts for AI agents.
* **REST** (FastAPI) — a normal HTTP/JSON API with Swagger docs.

```
City ─▶ Housing Scheme / Society ─▶ Block / Zone / Area ─▶ Property
                                   └────────────▶ Big Project  (mall, tower, mixed-use, compound, plaza)
CRM:  Agents ─▶ Leads ─▶ Customers ─▶ Deals ─▶ Tasks / Appointments / Interactions
```

## Files

| File | Purpose |
| --- | --- |
| `server.py` | **Single source of truth.** Data models, in-memory stores, business logic, seed data, and all MCP tools / resources / prompts. |
| `api.py` | FastAPI app. REST endpoints **reuse** the functions in `server.py`; also exposes MCP at `/mcp`. |
| `gis.py` | GIS engine (no portal data): base maps, geometry math, buffers, GeoJSON/KML builders, Leaflet map + choropleth HTML, report HTML, the news-ticker fragment, the layer store, the **routing engine** (walk / bicycle / motor car over a synthetic or supplied road network), and the **i18n + theme** layer (translations, theme tokens, language links, theme toggle JS). |
| `auth.py` | Authentication + **RBAC** (no MCP/FastAPI code): users, roles, the permission catalogue, OTP challenges, bearer sessions, password hashing, the notification outbox and the audit trail. |
| `content.py` | Portal **content & advertising engine** (no MCP/FastAPI code): content pages (mini-CMS), company history, contact directory, success stories and the advertisement book (categories, slots, targeting, scheduling, weighted rotation, performance). |
| `accounting.py` | Double-entry accounting + investment maths (no MCP/FastAPI code): chart of accounts, journal, invoices, payments, expenses, leases/rent roll, budgets, trial balance, P&L, balance sheet, cash flow, ratios, NPV/IRR/payback, cap rate, mortgage amortisation and ROI analysis. |
| `construction.py` | **Construction wing** (no MCP/FastAPI code): building types, 17 construction techniques/systems, 24 materials with live rates, BOQ element rates + rate analysis, an element-wise cost estimator (with preliminaries, contingency, consultancy, margin and escalation), phase timelines, material take-off, technique comparison, a build-quality → value/rent/payback impact model, site advisory (soil / seismic / height / budget), building codes & guidelines, the NOC/approval workflow, QA checklists and HSE rules. |
| `maintenance.py` | **Maintenance wing** (no MCP/FastAPI code): maintainable components with service life / replacement cost / criticality, maintenance services & trades with cost bands, a defect catalogue (symptoms, causes, repair, prevention), annual-cost estimation with a category breakdown and a capital-replacement reserve, preventive schedules, multi-year lifecycle reserve studies, condition assessment, repair-vs-replace analysis, warranty terms, inspection checklists, work orders and the value/rent/occupancy impact of maintenance. |
| `agents.py` | **Agentic OS** (no MCP/FastAPI code): the agent catalogue (8 roadmap *product* agents + specialist sub-agents), the eight products with priority (P0–P2), a **run engine** (plan → execute → review → deliver) with human-approval gates and a full audit trail, multi-agent orchestration, "Smart Actions" prioritisation, and move-likelihood / seller-intent scoring. Execution is delegated to a server-supplied `dispatch(tool, ctx)` so the same engine powers MCP *and* REST. |
| `transactions.py` | **Transactions** (no MCP/FastAPI code): the deal-to-close lifecycle — 10 stages, offer negotiation and counter-offers, contract-term extraction from agreement text, milestone/deadline checklists with RAG status, e-signature tracking by role, and on close a commission + VAT computation with a platform/agent **revenue-share split** returning a *balanced* journal entry and payouts. |
| `intelligence.py` | **Conversational buyer + seller pricing + investment screener** (no MCP/FastAPI code): natural-language requirement parsing (budgets incl. "crore"/"lakh"/"million", commute caps, bedrooms), weighted multi-factor candidate ranking with reasons, price-anomaly (z-score) scanning, affordability/DTI, an adjusted-comparable CMA with a price range + expected days-on-market, net-proceeds, listing-asset generation, and deal underwriting (cap rate, cash-on-cash, DSCR, after-tax cash flow, IRR/NPV/equity multiple) plus portfolio alerts. |
| `leasing.py` | **Autonomous Leasing** (no MCP/FastAPI code): rental units with a **holding-cost rent floor**, cross-channel inquiry classification and auto-replies (web chat / WhatsApp / SMS / e-mail / voice), tenant application screening (approve / conditional / decline), renewal recommendations, and a rent-collection board driven by the ledger. |
| `marketing.py` | **AI Marketing Conductor** (no MCP/FastAPI code): cross-channel lead capture and qualification (0–100 + band), rule-based routing by city/language/price/source to an agent + queue + SLA, dormant-lead re-engagement ("false negatives") with drafted outreach, six content formats (again approval-gated), and multichannel campaign planning with budget allocation and KPIs. |
| `commercial.py` | **Commercialization** (no MCP/FastAPI code): the 8-product catalogue with positioning, the 5 pricing models and 11 representative plans (**hybrid** subscription + usage + performance), per-call usage metering, usage-based billing with VAT, and performance revenue-share payouts. |
| `main.py` | Runs the combined server with uvicorn (REST + MCP on one port). |
| `test_integration.py` | Test app that exercises **both** MCP and FastAPI and checks the store is shared. |
| `smoke_http.py` | Starts the real uvicorn server and checks REST + the MCP `/mcp` handshake over the network. |
| `openai_facade.py` | OpenAI-compatible shim: `/v1/models`, `/v1/chat/completions`, `/v1/completions`, `/v1/embeddings`. |

Because every `@mcp.tool()` function is also a plain Python function, the REST
layer calls it directly — MCP and REST can never drift apart.

## Setup

```powershell
uv sync            # or: uv add fastapi "uvicorn[standard]" httpx
```

## Run

### 1. MCP only (stdio + MCP Inspector)

```powershell
uv run mcp dev server.py
# Inspector -> http://127.0.0.1:6274
```

### 2. REST + MCP together (recommended)

```powershell
uv run python main.py
# REST docs -> http://127.0.0.1:8000/docs
# MCP       -> http://127.0.0.1:8000/mcp   (Streamable HTTP)
# OpenAI    -> http://127.0.0.1:8000/v1    (models / chat / embeddings)
```

## OpenAI-compatible facade

If a client expects an OpenAI-style API (it probes `/v1/models`), point it at
`http://127.0.0.1:8000/v1`.

* **Local fallback (default)** — `/v1/chat/completions` answers from the portal's
  own catalogue via RAG, so it works with no external service. `/v1/embeddings`
  returns a deterministic hash embedding.
* **Proxy mode** — set these env vars to forward requests to a real
  OpenAI-compatible LLM (OpenAI, Ollama, LM Studio, vLLM, ...). Streaming is
  passed through:

  ```powershell
  $env:PORTAL_LLM_BASE_URL = "https://api.openai.com/v1"   # include /v1
  $env:PORTAL_LLM_API_KEY  = "sk-..."
  $env:PORTAL_LLM_MODEL    = "gpt-4o-mini"
  uv run python main.py
  ```

The portal's **tool** interface is still MCP at `/mcp`; the `/v1` facade is only
an LLM-compatible shim.

## MCP HTTP mode

`/mcp` runs in **stateless** mode by default (`PORTAL_MCP_STATELESS=1`). This
means no `Mcp-Session-Id` header is required, which fixes clients that fail with:

```json
{"jsonrpc":"2.0","id":null,"error":{"code":-32600,"message":"Bad Request: Missing session ID"}}
```

That error means the client didn't send back the session header from `initialize`.
Stateless mode removes the requirement entirely and is the right choice for a
tool-only server. To require sessions instead (e.g. if you need resumable streams):

```powershell
$env:PORTAL_MCP_STATELESS = "0"
uv run python main.py
```

Stateful clients (like the Python `mcp` client and the MCP Inspector) work in
either mode.

### 3. Tests

```powershell
uv run python test_integration.py   # in-process MCP client + FastAPI TestClient
uv run python smoke_http.py         # live uvicorn server + real HTTP
```

## Capabilities

* **Hierarchy** — CRUD + filtered search across cities, schemes, blocks and properties.
* **GIS** — Google-Earth-style base maps, master-plan/boundary/zone layers, spatial
  queries, buffers, thematic (choropleth) maps, KML/GeoJSON export, interactive map
  previews, cost/population/economic analysis and HTML reports (see below).
* **Predictions** — multi-factor (development, social, economic, political, regulatory,
  demand) index + scenario forecasts and a live real-estate news ticker (see below).
* **Units** — Marla / Kanal / SqFt / SqYd / Sqm / Acre conversion
  (1 Marla = 272.25 sqft, 1 Kanal = 20 Marla = 5445 sqft).
* **Memory layers** — near-memory cache + long-term memory (searches, views, favourites, preferences).
* **RAG** — natural-language retrieval over properties, schemes and projects, plus
  `investment_analysis` and `market_insights`.
* **Big projects** — malls / towers / mixed-use / compounds / plazas, with maps,
  floor plans, amenities and multimedia.
* **Images** — galleries for every entity type.
* **CRM** — agents, leads (scored), customers, deals pipeline, tasks, appointments and interactions.
* **Accounting** — a full **double-entry** ledger: chart of accounts, journal entries, receivable/payable
  invoices, payments, expenses, leases & rent roll, budgets with variance, trial balance, P&L,
  balance sheet, cash-flow statement and financial ratios (see below).
* **Investment / ROI** — NPV, IRR, payback, discounted payback, profitability index, equity multiple,
  cap rate, cash-on-cash, rental yields, mortgage amortisation and leveraged ROI with scenarios.
* **POI / AOI** — points of interest (schools, hospitals, malls, transit, parks …) with density and a
  distance-decayed **accessibility score**, plus saved **areas of interest** (radius / polygon / bbox /
  entity) that can be analysed, compared, mapped, reported and watched against the news.
* **Portal tools** — health, catalog, model schemas, runtime settings, an audit trail, federated
  `global_search`, portfolio statistics, availability and market trends.
* **Auth** — email/mobile accounts with **OTP-verified signup**, password or passwordless
  login, bearer sessions, password reset and an audit trail (`auth.py`).
* **Users & roles (RBAC)** — 19 system roles across public / client / staff / admin areas, a
  30-permission catalogue, per-user multi-role assignment and direct permission grants
  (see below).
* **Portal content** — a mini-CMS (about, mission, services, why-us, FAQ, team, careers,
  policies) plus a company-history timeline, a contact directory and success stories, all
  rendered into a bilingual portal home page (`content.py`).
* **Advertising** — creatives in named slots (hero, banner, sidebar, in-feed, footer,
  newsletter) tagged by category (smart technology, construction techniques, materials,
  solar, finance, security …) with targeting, scheduling, weighted rotation and
  impression / click / CTR tracking.
* **Routing** — best route + alternatives between two points or POIs **on foot, by
  bicycle or by motor car**, with distance, duration, turn-by-turn steps and an
  interactive route map.
* **Construction wing** — techniques/systems, materials with live rates, rate analysis,
  element-wise cost estimation, timelines, take-off, technique comparison, the impact of
  build quality on real-estate value/rent/payback, site advisory, building codes &
  guidelines, the approval workflow, QA and HSE (see below).
* **Maintenance wing** — components with service life, services & trades, a defect
  catalogue, annual-cost and reserve studies, preventive schedules, condition assessment,
  repair-vs-replace, warranties and work orders, plus the value/rent/occupancy impact of
  maintenance (see below).
* **Agentic OS** — an AI **agent layer** over one shared data layer: 24 agents
  (8 roadmap product agents + specialist sub-agents) with a plan → execute → review →
  deliver **run engine**, human-approval gates, a full audit trail, multi-agent
  orchestration, a prioritised **Smart-Actions** brief and move-likelihood / seller-intent
  scoring (see below). Agents call real portal tools through one `dispatch`, so the same
  functions are reachable from MCP.
* **Transactions** — the deal-to-close lifecycle wired to the ledger: offers &
  counter-offers, contract-term extraction, milestone deadlines with RAG status,
  e-signatures, and on close a commission + VAT split whose **balanced journal entry** is
  posted and payouts recorded (see below).
* **Buyer / seller / investor intelligence** — conversational requirement parsing and a
  weighted, explained shortlist; price-anomaly scanning; affordability/DTI; an
  adjusted-comp **CMA** with a price range and expected days-on-market; net-proceeds and
  listing assets; and a deal **underwriter** (cap rate, cash-on-cash, DSCR, after-tax cash
  flow, IRR/NPV/equity multiple) with portfolio alerts.
* **Autonomous leasing** — a 24/7 cross-channel leasing agent: inquiry handling, a
  holding-cost **rent floor**, application screening, renewal recommendations and a
  ledger-driven rent-collection board.
* **AI marketing conductor** — cross-channel lead qualification & routing, dormant-lead
  re-engagement, approval-gated content generation and campaign planning.
* **Commercialization** — the product catalogue, **hybrid pricing** (subscription + usage
  + performance), per-call metering, usage-based billing and revenue-share payouts.
* **Product surfaces** — the roadmap's named **MCP for Brokers** tools (`search_contacts`,
  `get_commission_projection`, `analyze_property_gis`, `create_listing_draft`) and
  **Property Intelligence** tools (`get_gis_score`, `get_accounting_snapshot`,
  `get_market_intelligence`, `score_seller_intent`), exposed over both protocols (see below).
* **Dual language + themes** — every HTML surface renders in **English or Urdu (RTL)** and
  in **auto / light / dark** themes, via shared CSS custom properties.

## GIS

The GIS engine lives in `gis.py` and is exposed in **both** MCP and REST.
Coordinate inputs to the tools below are `[lat, lon]` pairs; all GeoJSON output
uses the standard `[lon, lat]` order.

### Base maps

`gis_list_base_maps` / `GET /gis/base-maps` returns 8 selectable base maps —
Google Earth-style imagery plus open alternatives:

| id | provider |
| --- | --- |
| `google_satellite`, `google_hybrid`, `google_terrain`, `google_streets` | Google |
| `esri_world_imagery` | Esri / Maxar |
| `osm`, `opentopomap` | OpenStreetMap ecosystem |
| `carto_dark` | CARTO |

Each entry carries an XYZ `url_template`, `attribution` and `max_zoom`, ready for
Leaflet / MapLibre / QGIS.

### Layers (master plans, boundaries, zones)

A **layer** is a styled GeoJSON `FeatureCollection` attached to any entity
(`city` / `scheme` / `block` / `bigproject`) with a `layer_type` of
`master_plan`, `boundary`, `zone`, `plot_layout`, `road`, `green_area` or
`annotation`.

| MCP tool | REST |
| --- | --- |
| `gis_add_layer` | `POST /gis/layers` |
| `gis_list_layers` | `GET /gis/layers` |
| `gis_get_layer` | `GET /gis/layers/{id}` |
| `gis_update_layer` | `PUT /gis/layers/{id}` |
| `gis_delete_layer` | `DELETE /gis/layers/{id}` |
| `gis_add_master_plan` | `POST /gis/master-plans` |
| `gis_add_boundary` / `gis_add_zone` | `POST /gis/layers` |
| `gis_list_master_plans` | `GET /gis/master-plans` |

`gis_add_master_plan` anchors a housing-society/scheme/zone **master plan
raster** (and its source PDF) to a geographic rectangle (`north/south/east/west`),
so the layout lines up with real coordinates on the base map. If the entity has
no coordinates yet, they are set to the plan's centroid.

### Spatial queries & geometry

| MCP tool | REST |
| --- | --- |
| `gis_properties_in_bounds` | `GET /gis/properties-in-bounds` |
| `gis_properties_in_polygon` | `POST /gis/properties-in-polygon` |
| `gis_point_in_layer` | — |
| `gis_polygon_area` | `GET /gis/area` |
| `gis_polygon_centroid` | `GET /gis/centroid` |
| `gis_bearing` | `GET /gis/bearing` |
| `gis_destination` | — |
| `gis_distance_matrix` | `GET /gis/distance-matrix` |

### Export & preview

| MCP tool | REST | Output |
| --- | --- | --- |
| `gis_export_geojson` | `GET /gis/export/geojson/{entity_type}/{entity_id}` | GeoJSON FeatureCollection |
| `gis_export_kml` | `GET /gis/export/kml/{entity_type}/{entity_id}` | KML (opens in **Google Earth**) |
| `gis_map_preview` | `GET /gis/map/{entity_type}/{entity_id}` | Interactive Leaflet **HTML** with a base-map switcher |
| — | `GET /gis/map?lat=&lon=&zoom=&base_map=` | Leaflet HTML centred on a point |

MCP resources: `gis://basemaps`, `gis://layers/{entity_type}/{entity_id}`,
`gis://masterplans/{entity_type}/{entity_id}`, `gis://geojson/{entity_type}/{entity_id}`,
`gis://kml/{entity_type}/{entity_id}`, `gis://map/{entity_type}/{entity_id}`.

Seeded GIS data includes master plans for Lahore Smart City, Islamabad Smart City
and Bahria Town Karachi, a DHA Lahore boundary, plot-layout and commercial-zone
layers, and a boulevard line layer.

### Polygons, buffers & thematic maps

| MCP tool | REST |
| --- | --- |
| `gis_buffer_geometry` | `POST /gis/buffer` |
| `gis_buffer_point` | `GET /gis/buffer/point` |
| `gis_add_buffer_layer` | `POST /gis/buffers` |
| `gis_ring_analysis` | `GET /gis/ring-analysis` |
| `gis_polygon_analysis` | `POST /gis/polygon-analysis` |
| `gis_feature_table` | `GET /gis/features/{scope_type}/{scope_id}` |
| `gis_thematic_map` | `GET /gis/thematic/{scope_type}/{scope_id}` |
| `gis_analysis_assumptions` | `GET /gis/analysis/assumptions` |

`gis_thematic_map` renders a choropleth HTML map (quantile classes + palette) for any
metric; `gis_feature_table` returns the same numbers as rows for GIS/CAD export.
Available metrics: `property_count`, `market_value`, `avg_price`, `price_per_marla`,
`land_area_marla`, `built_area_sqft`, `population`, `density_per_sqkm`,
`development_cost`, `construction_cost`, `economic_output`, `jobs`,
`annual_property_tax`, `annual_rental_value`.

### Cost & development perspective

`gis_cost_development_analysis` ·
`GET /gis/analysis/{entity_type}/{entity_id}/cost-development`

A developer-grade feasibility view: gross development value (GDV), the cost build-up
(land + land development + infrastructure + construction), developer profit, profit
margin, project ROI, annualised ROI, cost per marla, break-even price/uplift, rental
payback, phased capex and a price × cost **sensitivity grid**. When a scheme declares
`total_units`, it also projects GDV, cost, margin and cost/value per unit.

Land cost uses listed plot prices when available, otherwise the editable
`LAND_COST_SHARE` (30% of GDV). Rates live in `GIS_ASSUMPTIONS`
(`GET /gis/analysis/assumptions`).

### Predictions & scenarios

`gis_forecast` · `GET /gis/analysis/{entity_type}/{entity_id}/forecast?years=5`

Blends seven weighted factor scores — **development, infrastructure, economic, social,
political, regulatory, demand** — plus live **news momentum** into a composite
Real-Estate Potential Index (0–100), then projects per year: price per marla, market
value, rental value, projected population and development cost. Four scenarios
(**optimistic / base / pessimistic / stress**, each with a probability) and a
probability-weighted **expected path** are returned with drivers, risk flags
(political / regulatory / infrastructure / economic), recommendations and a
confidence score. `gis_scenario_analysis` compares scenarios side by side;
`gis_market_factors` returns the raw factor scores.

### News ticker

Real-estate headlines are tracked across news, regulator, government, developer,
research and bank channels. Each item has a category (macro, policy, regulation,
market, development, infrastructure, political, social, finance), a sentiment and an
`impact_score` (−100…+100) that feeds the forecast's news momentum.

| MCP tool | REST | Output |
| --- | --- | --- |
| `news_add` | `POST /news` | created item |
| `news_list` | `GET /news?category=&city=&scheme=&days=` | filtered items |
| `news_channels` | `GET /news/channels` | channels + average impact |
| `news_impact` | `GET /news/impact?city=&scheme=` | sentiment + effect on the outlook |
| `news_ticker` | `GET /news/ticker` | scrolling ticker **HTML** fragment |
| — | `GET /news/ticker.html?city=` | standalone iframe-ready page |

### Reports (HTML)

| MCP tool | REST |
| --- | --- |
| `gis_area_report` | `GET /gis/report/{entity_type}/{entity_id}` |
| `gis_outlook_report` | `GET /gis/outlook/{entity_type}/{entity_id}` |

`gis_area_report` covers area, valuation, population, development cost and economic
impact. `gis_outlook_report` adds the cost/development perspective, the factor index,
the 5-year scenario predictions, drivers/risks/recommendations and a live news ticker.
Pass `include_outlook=true&include_news=true` to `GET /gis/report/...` to get the same
in one report, and `include_news=true` to `GET /gis/map/...` to pin the ticker to a map.

MCP resources: `gis://report/...`, `gis://cost/{entity_type}/{entity_id}`,
`gis://forecast/{entity_type}/{entity_id}`, `gis://outlook/{entity_type}/{entity_id}`,
`news://all`, `news://ticker`, `news://channels`, `news://impact`.

## Languages & themes (front-end facilities)

Every HTML surface — the interactive map, the printable reports and the news ticker —
supports **two languages** and **three themes**. Both are handled by `gis.py`, which is
data-agnostic, so MCP and REST share exactly the same rendering code.

| | values |
| --- | --- |
| Languages | `en` (English, LTR), `ur` (اردو, RTL) |
| Themes | `auto` (follow the OS), `light`, `dark` |

* **Translation** — text is looked up in `gis.TRANSLATIONS` (English source string →
  Urdu) and falls back to English for anything unmapped, so adding a language is one
  more dictionary entry. A few dynamic strings (the forecast heading, factor pills like
  `economic (72/100)`, the recommendation sentences) are handled by regex rules.
* **RTL** — Urdu flips `<html dir="rtl">` and swaps in a Nastaliq-capable font stack;
  table alignment and ticker direction follow suit.
* **Theming** — colours are CSS custom properties in `gis.THEME_TOKENS`. The page emits
  `:root` tokens plus `html[data-theme="light"|"dark"]` overrides (higher specificity, so
  the client toggle always wins) and a `@media (prefers-color-scheme: dark)` block only
  for `auto`. The in-page toggle cycles auto → light → dark, persists the choice in
  `localStorage` (`portal-theme`) and pushes it into any embedded map iframe. The ticker
  uses `var(--ticker-*, fallback)` colours, so it still looks right when embedded anywhere.
* **Switching** — the language links are plain `?lang=xx` links that merge the existing
  query string in JavaScript. Inside an embedded map `srcdoc` iframe they are hidden
  (`gis_map_preview(..., lang_links=False)`) because the parent page owns the theme.

| MCP tool | REST |
| --- | --- |
| `portal_languages` | `GET /i18n/languages` |
| `portal_themes` | `GET /ui/themes` |
| `portal_strings` | `GET /i18n/strings/{lang}` |

MCP resources: `gis://languages`, `gis://themes`, `gis://strings/{lang}`.

Every HTML-producing MCP tool (`gis_map_preview`, `gis_thematic_map`, `gis_area_report`,
`gis_outlook_report`, `news_ticker`) and every HTML REST route therefore accepts

```text
?lang=en|ur        # explicit language  (REST also honours the Accept-Language header)
?theme=auto|light|dark
```

## Accounting, finance & ROI

`accounting.py` is a self-contained, dependency-free double-entry engine (PKR by default).
Every posting is a balanced journal entry; the statements are always derived from the ledger,
so REST and MCP report identical numbers from the same in-memory books.

* **Chart of accounts** — ~39 seeded accounts across asset / liability / equity / income / expense
  (cash `1010`, bank, escrow, AR `1100`, land `1200`, buildings `1300`, accumulated depreciation
  `1350`, AP `2000`, bank loan `2200`, share capital `3000`, retained earnings `3100`, rent `4000`,
  service charges `4020`, commission `4030`, parking `4040`, salaries `5000`, utilities `5010`,
  maintenance `5020`, management `5030`, marketing `5040`, depreciation `5070`, …).
* **Billing** — receivable/payable invoices with per-line or invoice-level tax (GST 17%),
  automatic ledger posting, partial payments, multi-method receipts/disbursements and
  ageing buckets (current / 1-30 / 31-60 / 61-90 / 90+).
* **Leases & rent roll** — recurring leases (monthly / quarterly / annual) with escalation and
  security deposits; `accounting_generate_rent_invoices` raises the period's rent invoices
  idempotently per lease-month.
* **Budgets** — budget vs actual variance with favourable/unfavourable flags.
* **Statements** — trial balance, general ledger (running balance), P&L (optionally scoped to a
  property / scheme / city), balance sheet, cash-flow statement (operating / investing / financing)
  and financial ratios (current, quick, D/E, ROE, ROA, margins).

| MCP tool | REST |
| --- | --- |
| `accounting_info` | `GET /accounting/info` |
| `accounting_chart_of_accounts` | `GET /accounting/accounts`, `/accounting/chart` |
| `accounting_create_account` / `accounting_update_account` | `POST /accounting/accounts`, `PUT /accounting/accounts/{code}` |
| `accounting_account_balance` | `GET /accounting/accounts/{code}/balance` |
| `accounting_journal_post` / `accounting_journal_list` / `accounting_journal_get` / `accounting_journal_void` | `POST`/`GET /accounting/journal`, `GET /accounting/journal/{id}`, `POST /accounting/journal/{id}/void` |
| `accounting_trial_balance` | `GET /accounting/trial-balance` |
| `accounting_general_ledger` | `GET /accounting/ledger/{account_code}` |
| `accounting_profit_and_loss` / `accounting_balance_sheet` / `accounting_cash_flow` | `GET /accounting/profit-and-loss`, `/balance-sheet`, `/cash-flow` |
| `accounting_ratios` / `accounting_dashboard` | `GET /accounting/ratios`, `/dashboard` |
| `accounting_invoice_create` / `_list` / `_get` / `_post` | `POST`/`GET /accounting/invoices`, `GET /accounting/invoices/{id}`, `POST /accounting/invoices/{id}/post` |
| `accounting_payment_record` / `accounting_expense_create` | `POST /accounting/payments`, `/expenses` |
| `accounting_invoice_aging` | `GET /accounting/aging` |
| `accounting_lease_create` / `_list` / `accounting_rent_roll` / `accounting_generate_rent_invoices` | `POST`/`GET /accounting/leases`, `GET /accounting/rent-roll`, `POST /accounting/rent-invoices` |
| `accounting_budget_create` / `_list` / `accounting_budget_variance` | `POST`/`GET /accounting/budgets`, `GET /accounting/budgets/{id}/variance` |
| `accounting_property_performance` | `GET /accounting/properties/{id}/performance` |

**Investment maths (ROI).**

| MCP tool | REST | Returns |
| --- | --- | --- |
| `finance_mortgage_calculator` | `GET /finance/mortgage` | periodic payment, total interest, amortisation schedule |
| `finance_investment_metrics` | `POST /finance/investment-metrics` | NPV, IRR, payback, discounted payback, PI, equity multiple, ROI |
| `finance_cap_rate` / `finance_cash_on_cash` | `GET /finance/cap-rate`, `/cash-on-cash` | cap rate · cash-on-cash |
| `finance_roi_analysis` | `POST /finance/roi` | leveraged ROI with pessimistic / base / optimistic scenarios |
| `finance_property_roi` | `POST /finance/property-roi` | gross/net yield, appreciation, leverage, IRR, exit proceeds |
| `finance_rental_yield` | `GET /finance/rental-yield/{property_id}` | gross/net yield + cap rate for a listed property |
| `finance_portfolio_roi` | `GET /finance/portfolio-roi` | portfolio value, rent, NOI, yields and leveraged ROI |

MCP resources: `accounting://config`, `accounting://chart-of-accounts`, `accounting://trial-balance`,
`accounting://dashboard`, `accounting://invoices`, `accounting://rent-roll`.
MCP prompts: `financial_review_prompt`, `roi_review_prompt`.

The books are seeded with ~14 months of transactions (share capital, an acquisition, a term loan,
four leases, seven months of rent invoices with partial collection, six months of operating expenses,
depreciation, service-charge/parking/commission income, a payable bill and an operating budget),
so every statement returns meaningful figures out of the box.

## Points of interest (POI) & areas of interest (AOI)

**POI** — nearby facilities that drive liveability: education, health, shopping, worship, transport,
park, restaurant, bank, fuel, government, hotel, sports and other.

| MCP tool | REST |
| --- | --- |
| `poi_add` / `poi_update` / `poi_delete` | `POST`, `PUT /poi/{id}`, `DELETE /poi/{id}` |
| `poi_list` / `poi_get` / `poi_categories` | `GET /poi`, `GET /poi/{id}`, `GET /poi/categories` |
| `poi_nearby` / `poi_nearest` / `poi_within_polygon` | `GET /poi/nearby`, `/poi/nearest`, `POST /poi/within-polygon` |
| `poi_density` / `poi_accessibility_score` | `GET /poi/density/{type}/{id}`, `GET /poi/accessibility` |
| `poi_map` | `GET /poi/map` |

`poi_accessibility_score` blends every POI within a radius with a category weight and an
exponential distance decay into a **0-100 liveability score** (excellent / good / fair / poor),
broken down by category. The same POIs can be layered onto `gis_map_preview(include_poi=True)`.

**AOI** — a saved, analysable footprint with one of four geometries:

| kind | inputs |
| --- | --- |
| `circle` | `center_latitude`, `center_longitude`, `radius_m` |
| `polygon` | `coordinates` (`[[lat, lon], …]`) |
| `bbox` | `bounds` (`{south, west, north, east}`) |
| `entity` | `entity_type` + `entity_id` (city / scheme / block / bigproject) |

| MCP tool | REST |
| --- | --- |
| `aoi_create` / `aoi_update` / `aoi_delete` | `POST /aoi`, `PUT /aoi/{id}`, `DELETE /aoi/{id}` |
| `aoi_list` / `aoi_get` | `GET /aoi`, `GET /aoi/{id}` |
| `aoi_stats` / `aoi_analyze` | `GET /aoi/{id}/stats`, `/aoi/{id}/analyze` |
| `aoi_compare` | `POST /aoi/compare` |
| `aoi_watch` | `GET /aoi/{id}/watch` |
| `aoi_map` / `aoi_report` | `GET /aoi/{id}/map`, `/aoi/{id}/report` |

`aoi_analyze` returns the full picture in one call: area & valuation, population and density,
development cost and economic impact, the POI mix + accessibility, the seven-factor index and the
5-year scenario forecast. `aoi_watch` filters the news to the area's `watch_categories` and raises
alerts when `impact_score` crosses `watch_alert_threshold`. `aoi_report` renders the whole thing as a
printable HTML report (with a live ticker and an embedded map) in either language and theme.

MCP resources: `poi://all`, `poi://categories`, `aoi://all`, `aoi://categories`.
MCP prompts: `aoi_due_diligence_prompt`, `site_selection_prompt`.

## Portal discovery, settings & federated search

| MCP tool | REST |
| --- | --- |
| `portal_health` | `GET /portal/health` |
| `portal_catalog` | `GET /portal/catalog` |
| `portal_schema` | `GET /portal/schema?model=` |
| `portal_settings` | `GET` / `PUT /portal/settings` |
| `portal_audit_log` | `GET /portal/audit` |
| `global_search` | `GET /portal/search?query=` |
| `portal_statistics` | `GET /portal/statistics` |
| `property_availability` | `GET /portal/availability` |
| `market_trends` | `GET /portal/market-trends` |

`portal_catalog` enumerates every registered MCP tool (grouped), resource, template and prompt —
the live inventory of the whole surface. `portal_settings` reads and edits the runtime assumptions
(`GIS_ASSUMPTIONS`), the forecast constants, and the accounting/auth configs. `global_search` fans a
query across cities, schemes, blocks, properties, big projects, POIs, AOIs, news and the CRM.

MCP resources: `portal://health`, `portal://catalog`, `portal://settings`, `portal://statistics`.
MCP prompts: `market_briefing_prompt`, `data_onboarding_prompt`.

## Authentication (email / mobile + OTP-verified signup)

Accounts live in `auth.py` (dependency-free: PBKDF2 password hashing, random OTPs and
opaque bearer sessions — no SMS/e-mail provider is needed because messages are written
to an in-memory **outbox** that the tests read back).

**Signup is OTP-gated.** A new account is created in `pending` status and only becomes
`active` — and only then able to log in — once a code from the signup challenge is
verified.

| MCP tool | REST |
| --- | --- |
| `auth_signup` | `POST /auth/signup` |
| `auth_verify_otp` | `POST /auth/verify-otp` |
| `auth_resend_otp` | `POST /auth/resend-otp` |
| `auth_login` | `POST /auth/login` |
| `auth_request_otp` / `auth_verify_login_otp` | `POST /auth/otp/request` / `POST /auth/otp/verify` |
| `auth_request_password_reset` / `auth_reset_password` | `POST /auth/password/reset-request` / `POST /auth/password/reset` |
| `auth_set_password` | `POST /auth/password/set` *(Bearer)* |
| `auth_me` | `GET /auth/me` *(Bearer)* |
| `auth_logout` / `auth_refresh` | `POST /auth/logout` / `POST /auth/refresh` *(Bearer)* |
| `auth_list_users` | `GET /auth/users` *(Bearer)* |
| `auth_get_otp` / `auth_notifications` / `auth_events` / `auth_config` | `GET /auth/otps`, `/auth/notifications`, `/auth/events`, `/auth/config` |

* **Identifiers** — supply an email, a mobile, or both. Mobiles are normalised to E.164
  (`0321 9998877` → `+923219998877`); emails are lower-cased.
* **OTP policy** — 6 digits, 5-minute TTL, 5 attempts, a 30-second resend cooldown and a
  cap of 10 codes per identifier per hour. Codes are stored salted-hashed; the plaintext
  is kept only while `PORTAL_AUTH_EXPOSE_OTP` is on (default, for local dev) and is
  returned as `dev_otp` so the flow can be driven without a real gateway.
* **Sessions** — opaque `secrets.token_urlsafe` tokens, 24-hour expiry, revocable;
  a password reset revokes every existing session.
* **Guarded routes** — `/auth/me`, `/auth/logout`, `/auth/refresh`, `/auth/users` and
  `/auth/password/set` require `Authorization: Bearer <token>` (HTTP `401` otherwise).
  `require_user` in `api.py` is the ready-made FastAPI dependency for protecting more.
* **CRM link** — a successful signup also creates a CRM customer and stores
  `customer_id` on the account.
* **Seeded demo accounts** — 13 accounts covering every tier (all `active`, password shown):
  `admin@portal.pk`/`Admin@12345` (super_admin), `auditor@portal.pk`/`Auditor@12345`,
  `agent@portal.pk`/`Agent@12345`, `developer@portal.pk`/`Developer@12345`,
  `finance@portal.pk`/`Finance@12345` (finance_manager + accountant),
  `content@portal.pk`/`Content@12345`, `ads@portal.pk`/`Ads@12345`,
  `valuer@portal.pk`/`Valuer@12345`, `support@portal.pk`/`Support@12345`,
  `investor@portal.pk`/`Investor@12345`, `landlord@portal.pk`/`Landlord@12345`,
  `tenant@portal.pk`/`Tenant@12345` and `bilal@example.com`/`Buyer@12345` (buyer).

MCP resources: `auth://users`, `auth://config`, `auth://otps`, `auth://events`.

```powershell
# curl equivalent of the signup → verify → use-token flow
curl -X POST http://127.0.0.1:8000/auth/signup -H "Content-Type: application/json" `
  -d '{"email":"me@example.com","mobile":"03219998877","password":"Secret@123","name":"Me","role":"buyer"}'
curl -X POST http://127.0.0.1:8000/auth/verify-otp -H "Content-Type: application/json" `
  -d '{"identifier":"me@example.com","code":"123456"}'
curl http://127.0.0.1:8000/auth/me -H "Authorization: Bearer <token>"
```

## Users, roles & permissions (RBAC)

`auth.py` carries a full role-based access-control layer. There are **19 system roles**
grouped into four portal areas, and a catalogue of **30 permissions** written as
`resource.action` (for example `listings.manage`, `accounting.manage`, `ads.manage`).

| Portal area | Roles |
| --- | --- |
| **admin** | `super_admin`, `admin`, `auditor` |
| **staff** | `moderator`, `developer`, `agency_manager`, `agent`, `valuer`, `finance_manager`, `accountant`, `content_editor`, `ad_manager`, `customer_support` |
| **client** | `investor`, `seller`, `landlord` |
| **public** | `buyer`, `tenant`, `user` |

A user holds a **list of roles** (so `finance@portal.pk` can be both a finance manager and an
accountant), which resolves to a union of permissions. Individual extra permissions can also be
granted directly, on top of the roles. The highest-level role is the user's *primary* role.

| MCP tool | REST |
| --- | --- |
| `auth_list_roles` / `auth_get_role` / `auth_role_summary` | `GET /roles`, `GET /roles/{name}`, `GET /roles/summary` |
| `auth_permissions` | `GET /roles/permissions` |
| `auth_create_role` / `auth_update_role` / `auth_delete_role` | `POST /roles`, `PUT /roles/{name}`, `DELETE /roles/{name}` |
| `auth_users_by_role` | `GET /roles/{name}/users` |
| `auth_user_roles` / `auth_user_permissions` | `GET /users/{id}/roles`, `GET /users/{id}/permissions` |
| `auth_set_user_roles` | `PUT /users/{id}/roles` |
| `auth_assign_role` / `auth_revoke_role` | `POST /users/{id}/roles`, `DELETE /users/{id}/roles/{role}` |
| `auth_grant_permission` / `auth_revoke_permission` / `auth_check_permission` | `POST` / `DELETE /users/{id}/permissions[/{perm}]`, `GET /users/{id}/permissions/check` |

System roles are protected from deletion and from permission edits; create a **custom role**
with `auth_create_role` for bespoke access. When signing up, `role` must be one of the
self-service `SIGNUP_ROLES` (`buyer`, `tenant`, `seller`, `landlord`, `investor`, `user`).

MCP resources: `roles://all`, `roles://role/{name}`, `roles://permissions`, `roles://summary`,
`roles://user/{user_id}`. Prompts: `role_assignment_prompt`.

## Portal content & advertising

`content.py` is a small CMS plus an advertising engine; `gis.py` renders it into the themed,
bilingual **portal home page**. The `PORTAL_LAYOUT` interleaves editorial blocks (about,
services, why-us), the company-history timeline, success stories and the contact directory
with **advertisement sections**, so the sponsored slots are decorated into the reading flow.

| MCP tool | REST |
| --- | --- |
| `content_overview` | `GET /content/overview` |
| `content_page_list` / `content_page_get` | `GET /content/pages`, `GET /content/pages/{key}` |
| `content_page_create` / `content_page_update` / `content_page_delete` | `POST`, `PUT`, `DELETE /content/pages[/{key}]` |
| `content_history` / `content_history_add` | `GET`, `POST /content/history` |
| `content_contact` / `content_contact_add` | `GET`, `POST /content/contacts` |
| `content_success_stories` / `content_success_story_add` | `GET`, `POST /content/stories` |
| `content_navigation` / `content_site` | `GET /content/navigation`, `GET /content/site` |
| `content_portal_home` | `GET /portal/home`, `GET /portal/home.html` |

Advertising is managed separately — creatives are placed in named **slots** and tagged by
**category**, then rotated by priority and by a deliverable-weighted exposure share.

| MCP tool | REST |
| --- | --- |
| `ad_categories` / `ad_slots` | `GET /ads/categories`, `GET /ads/slots` |
| `ad_list` / `ad_get` / `ad_active` | `GET /ads`, `GET /ads/{id}`, `GET /ads/active` |
| `ad_create` / `ad_update` / `ad_delete` | `POST /ads`, `PUT /ads/{id}`, `DELETE /ads/{id}` |
| `ad_section` / `ad_preview` | `GET /ads/section`, `GET /ads/preview` |
| `ad_track` / `ad_performance` / `ad_report` | `POST /ads/{id}/track`, `GET /ads/performance`, `GET /ads/report` |

* **Categories** — `smart_technology`, `construction_technique`, `materials`,
  `tools_equipment`, `solar_energy`, `water`, `security`, `elevators`, `interiors`,
  `landscaping`, `finance`, `insurance`, `legal`, `services`.
* **Slots** — `hero`, `banner`, `sidebar`, `infeed`, `footer`, `newsletter`.
* **Targeting & scheduling** — target by city / scheme / language and set a `valid_from` /
  `valid_until` window; a spent `budget` auto-pauses a creative.
* **Tracking** — impressions, clicks, CTR, spend and remaining budget, per ad, per slot and
  per category; the portal front end emits `data-ad-id` / `data-ad-event` hooks.
* The seed carries **23 creatives** (including Urdu-language ones) across every category and
  slot — smart-home automation, tunnel-form and ICF construction, cement / steel availability,
  solar net metering, Islamic home finance, security, lifts, interiors and more.

MCP resources: `content://overview`, `content://pages`, `content://page/{key}`,
`content://history`, `content://contacts`, `content://stories`, `content://site`,
`content://portal-home`, `ads://categories`, `ads://slots`, `ads://all`, `ads://active`,
`ads://performance`. Prompts: `content_review_prompt`, `ad_campaign_prompt`.

## Routing (on foot / bicycle / motor car)

The routing engine in `gis.py` returns the **best route plus alternatives** between two
coordinates or two POIs, for three travel modes, each with distance, duration, turn-by-turn
steps, a per-road-class breakdown and a drawable geometry.

| MCP tool | REST |
| --- | --- |
| `gis_travel_modes` / `gis_road_classes` | `GET /gis/travel-modes`, `GET /gis/road-classes` |
| `gis_route` | `GET /gis/route` |
| `gis_route_compare` | `GET /gis/route/compare` |
| `gis_route_matrix` | `POST /gis/route/matrix` |
| `poi_route` | `GET /poi/route` |
| `gis_route_map` | `GET /gis/route/map` |
| `gis_add_road_network` / `gis_list_road_networks` | `POST`, `GET /gis/road-networks` |

* **Modes** — `walk` (on foot), `bike` (bicycle) and `drive` (motor car). Road classes
  (motorway, arterial, secondary, local, residential, service, footpath, steps, track)
  carry a per-mode speed; a `0` speed bars that mode from the class (pedestrians can't
  use a motorway, cars can't use steps).
* **Best & alternatives** — the graph is searched by *travel time* (Dijkstra); alternatives
  come from Yen's loopless *k*-shortest-paths so genuinely different routes are offered,
  each annotated with its extra distance and time versus the best.
* **Network** — routes run on a synthetic street grid (arterials every few blocks) generated
  locally around the points, over a city / scheme scope, or on a **custom network** you
  register with `gis_add_road_network` (polylines with a `road_class`).
* **Traffic** — `traffic_factor` scales driving times only (default `1.25`).
* **`poi_route`** resolves POIs by id or name; `gis_route_matrix` builds a full
  distance/time matrix across several POIs or coordinates; `gis_route_map` draws the best
  route and its alternatives (plus a per-mode comparison) on an interactive Leaflet map.

MCP resource: `routes://config`. Prompt: `route_planning_prompt`.

```powershell
# best driving route (JSON)
curl "http://127.0.0.1:8000/gis/route?origin_latitude=31.4504&origin_longitude=74.2810&destination_latitude=31.4690&destination_longitude=74.4120&mode=drive&alternatives=2"
# on foot between two POIs
curl "http://127.0.0.1:8000/poi/route?origin_poi=Smart%20City%20Public%20School&destination_poi=Downtown%20Shopping%20Mall&mode=walk"
# route map (HTML)
curl "http://127.0.0.1:8000/gis/route/map?origin_latitude=31.4504&origin_longitude=74.2810&destination_latitude=31.4690&destination_longitude=74.4120&mode=drive" -o route.html
```

## Construction wing

`construction.py` turns a plot and a brief into a defensible build cost, and treats the
build decision as an investment decision. It is exposed in full over **both** MCP and REST,
and its portal page (`/construction/portal`) is an interactive, bilingual, themed report.

### Techniques, materials & rates

| MCP tool | REST |
| --- | --- |
| `construction_overview` | `GET /construction/overview` |
| `construction_techniques` / `construction_technique` | `GET /construction/techniques[/{key}]` |
| `construction_materials` / `construction_material` | `GET /construction/materials[/{key}]` |
| `construction_element_rates` | `GET /construction/element-rates` |
| `construction_rate_analysis` | `GET /construction/rate-analysis` |
| `construction_trades` | `GET /construction/trades` |

* **Techniques (17)** — RCC frame, load-bearing masonry, steel frame, pre-engineered
  building (PEB), precast, tunnel form, ICF, AAC block, brick-and-block, curtain-wall /
  ACP facade, brick-clad, RCC/steel/truss roofing, drywall partition and green/bamboo —
  each scored on cost factor, build speed, material/labour intensity, soil and seismic
  suitability, equipment, pros/cons, sustainability, warranty and code references.
* **Materials (24)** — cement types, steel bars, sand/aggregate, bricks/blocks, tiles,
  paint, glass, aluminium/UPVC, ACP, waterproofing, insulation, timber, MEP fittings and
  more — with unit, live unit rate, wastage %, lead time, local availability, alternatives
  and an eco-rating.
* **Element rates (16)** — substructure, frame, masonry, roofing, plaster, flooring,
  ceiling, doors/windows, painting, plumbing, electrical, HVAC, fire, lifts, external
  works and landscaping — each with a material / labour / plant / overhead split
  (`construction_rate_analysis`).
* **Quality tiers** — economy / standard / premium / luxury base rates (Rs 3,300 → 9,500
  per sqft) multiplied by building-type and city factors, a floor premium and escalation.

### Estimation, timelines & take-off

| MCP tool | REST |
| --- | --- |
| `construction_estimate` | `POST /construction/estimate` |
| `construction_timeline` | `GET /construction/timeline` |
| `construction_takeoff` | `GET /construction/takeoff` |
| `construction_compare` | `GET /construction/compare` |
| `construction_estimate_save` / `_estimates` / `_estimate_get` | `POST`/`GET /construction/estimates[/{id}]` |

`construction_estimate` builds the cost up **element by element** (shares are base-normalised
so they always total 100%), then adds preliminaries, contingency and consultancy percentages
plus contractor overhead & profit, and returns totals, cost per sqft, a phase timeline and a
material take-off. `construction_compare` ranks competing techniques by cost and build speed;
`construction_takeoff` returns cement, steel, sand, aggregate, bricks, tiles and paint with
wastage. A 10-marla G+1 standard house in Lahore estimates at about **Rs 15.22M** (≈ Rs 5,590/sqft)
over ≈ 381 days.

### Real-estate impact, advisory & guidelines

| MCP tool | REST |
| --- | --- |
| `construction_impact` | `GET /construction/impact` |
| `construction_advisory` | `GET /construction/advisory` |
| `construction_guidelines` | `GET /construction/guidelines` |
| `construction_approvals` | `GET /construction/approvals` |
| `construction_qa` | `GET /construction/qa` |
| `construction_hse` | `GET /construction/hse` |

* **Impact** — moving up a quality tier lifts market value and rent by a tier-specific
  premium (standard +4.5%, premium +10%, luxury +17%); `construction_impact` reports the
  extra build cost, the value uplift, the rent uplift and the payback period.
* **Advisory** — given plot area, soil type (sandy loam, clay, silt, rock, fill …), seismic
  zone, height and budget, it recommends a technique and foundation, and flags the codes
  that apply.
* **Guidelines (12)** — zoning & setbacks, FAR/height, structural design, seismic detailing,
  fire, accessibility, environmental, material standards and HSE, each with its authority
  and code reference. `construction_approvals` gives the NOC/approval workflow (steps,
  authority, documents, durations); `construction_qa` and `construction_hse` give the QA and
  site-safety checklists.

MCP resources: `construction://overview`, `construction://techniques`,
`construction://technique/{key}`, `construction://materials`,
`construction://element-rates`, `construction://guidelines`, `construction://approvals`,
`construction://trades`. Prompts: `construction_estimate_prompt`, `construction_advisory_prompt`.

```powershell
# element-wise estimate (JSON)
curl -X POST "http://127.0.0.1:8000/construction/estimate" -H "Content-Type: application/json" `
  -d '{"covered_area":2722.5,"floors":2,"building_type":"house","quality_tier":"standard"}'
# the Construction wing page (also ?lang=ur&theme=dark)
start "http://127.0.0.1:8000/construction/portal"
```

## Maintenance wing

`maintenance.py` covers a building's whole lifecycle after handover — preventive schedules,
condition, repair-vs-replace, annual cost and reserve studies, service providers, defect
diagnosis — and quantifies the value of maintaining an asset. It is exposed over **both**
MCP and REST, with an interactive portal page at `/maintenance/portal`.

### Components, services & defects

| MCP tool | REST |
| --- | --- |
| `maintenance_overview` | `GET /maintenance/overview` |
| `maintenance_components` / `maintenance_component` | `GET /maintenance/components[/{key}]` |
| `maintenance_services` / `maintenance_service` | `GET /maintenance/services[/{key}]` |
| `maintenance_defects` / `maintenance_defect` | `GET /maintenance/defects[/{key}]` |

* **Components (19)** — structure, roof waterproofing, external walls, plaster, paint,
  flooring, ceilings, doors/windows, plumbing, sanitary, electrical, HVAC, lifts, fire
  systems, water tanks, bore/pumps, boundary, landscaping and general services — each with a
  service life, replacement cost %, criticality, inspection frequency and periodic tasks.
* **Services (18)** — plumbing, electrical, AC/HVAC, waterproofing, painting, carpentry,
  masonry, welding, glazing, pest control, cleaning, landscaping, lift, generator/UPS, solar,
  security, roof and general handyman — with unit, cost band, emergency flag and response time.
* **Defects (15)** — seepage, dampness, cracks, spalling, corrosion, efflorescence, plumbing
  leaks, electrical faults, HVAC faults, lift faults, paint peeling, tile debonding, termites,
  settlement and roof leaks — with symptoms, causes, severity, diagnosis, repair method, cost
  band, urgency and prevention.

### Cost, lifecycle & condition

| MCP tool | REST |
| --- | --- |
| `maintenance_estimate` | `GET /maintenance/estimate` |
| `maintenance_schedule` | `GET /maintenance/schedule` |
| `maintenance_lifecycle` / `maintenance_reserve` | `GET /maintenance/lifecycle`, `GET /maintenance/reserve` |
| `maintenance_condition` | `GET /maintenance/condition` |
| `maintenance_repair_estimate` / `maintenance_repair_or_replace` | `GET /maintenance/repair-estimate`, `GET /maintenance/repair-or-replace` |

`maintenance_estimate` returns the annual routine cost (PKR/sqft/yr by property type ×
quality × AMC tier, with an age factor), a category breakdown and the **capital-replacement
reserve**. `maintenance_lifecycle` projects replacements year by year (inflated) and
`maintenance_reserve` gives the annual sinking-fund contribution. `maintenance_schedule`
lays tasks onto a 12-month calendar; `maintenance_condition` scores 1–5 per area into a band;
`maintenance_repair_or_replace` compares a 5-year repair vs replacement plan. A 2,000-sqft
house aged 8 years on a standard AMC estimates at about **Rs 66.1K/yr** (≈ Rs 33/sqft/yr)
plus a ≈ Rs 319K/yr reserve.

### Impact, guidelines & work orders

| MCP tool | REST |
| --- | --- |
| `maintenance_impact` | `GET /maintenance/impact` |
| `maintenance_guidelines` / `maintenance_warranty` / `maintenance_inspection` | `GET /maintenance/guidelines`, `/warranty`, `/inspection` |
| `maintenance_plan_save` / `_plans` / `_plan_get` | `POST`/`GET /maintenance/plans[/{id}]` |
| `maintenance_work_order_create` / `_work_orders` / `_work_order_get` / `_work_order_update` | `POST`/`GET`/`PUT /maintenance/work-orders[/{id}]` |

* **Impact** — a well-maintained asset (vs deferred) sells faster and at a higher value, lets
  faster and at a higher rent, and retains tenants longer; `maintenance_impact` quantifies the
  value uplift, rent uplift, yield change and occupancy/retention effect.
* **AMC tiers** — basic (1.0×), standard (1.3×) and comprehensive (1.7×) agreements with
  scheduled preventive visits and response-time guarantees.
* **Work orders** — raise, list, fetch and update maintenance jobs (status, priority, assignee,
  estimated cost) as a small service-desk.

MCP resources: `maintenance://overview`, `maintenance://components`,
`maintenance://component/{key}`, `maintenance://services`, `maintenance://defects`,
`maintenance://defect/{key}`, `maintenance://guidelines`, `maintenance://warranty`,
`maintenance://condition-scale`. Prompts: `maintenance_plan_prompt`, `maintenance_incident_prompt`.

```powershell
# annual cost + reserve (JSON)
curl "http://127.0.0.1:8000/maintenance/estimate?covered_area=2000&age_years=8"
# the Maintenance wing page (also ?lang=ur&theme=dark)
start "http://127.0.0.1:8000/maintenance/portal"
```

## Agentic OS & the eight products

The roadmap's eight future products are delivered as six framework-free domain modules —
`agents.py`, `transactions.py`, `intelligence.py`, `leasing.py`, `marketing.py` and
`commercial.py`. **Every capability below is exposed both as MCP tools/resources/prompts and
as REST endpoints**, and both layers call the exact same functions in `server.py`.

| Priority | Product | Delivered by |
| --- | --- | --- |
| P0 | **Property Intelligence MCP Server** | `intelligence.py` + the GIS/POI/AOI tools |
| P0 | **MCP for Brokers** | `agents.py` (the `dispatch` loop exposes real tools to any MCP client) |
| P0 | **Broker AI Workspace (Agentic OS)** | `agents.py` + all CRM/accounting tools |
| P1 | **Conversational Homebuying Agent** | `intelligence.py` (buyer) |
| P1 | **Seller Intelligent Pricing & Marketing Agent** | `intelligence.py` (seller) |
| P1 | **AI Marketing Conductor** | `marketing.py` |
| P2 | **Agentic Investment Screener** | `intelligence.py` (investment) |
| P2 | **Autonomous Leasing Agent** | `leasing.py` |

See the five wing pages in a browser — **Agentic OS**, **Autonomous Leasing**,
**AI Marketing Conductor** and **Commercialization** (each also `?lang=ur&theme=dark`):

```powershell
start "http://127.0.0.1:8000/agents/portal"
start "http://127.0.0.1:8000/leasing/portal"
start "http://127.0.0.1:8000/marketing/portal"
start "http://127.0.0.1:8000/commercial/portal"
```

### Agentic OS — agents, runs & smart actions

The run engine executes **plan → execute → review → deliver** steps, bound to real portal
tools. Set `approve=false` to pause at the human-approval gate and finish with
`agent_approve`. Every run, step and approval is recorded.

**MCP tools:** `agents_overview`, `agents_catalog`, `agent_get`, `agent_products`,
`agent_plan`, `agent_run`, `agent_runs`, `agent_run_get`, `agent_approve`,
`agent_smart_actions`, `agent_move_likelihood`, `agent_seller_intent`, `agent_orchestrate`,
`agentic_portal`.

**REST:** `GET /agents/overview`, `GET /agents/catalog`, `GET /agents/products`,
`GET /agents/{key}`, `GET /agents/runs`, `GET /agents/runs/{run_id}`,
`POST /agents/plan`, `POST /agents/run`, `POST /agents/runs/{run_id}/approve`,
`GET /agents/smart-actions`, `GET /agents/move-likelihood/{lead_id}`,
`GET /agents/seller-intent`, `POST /agents/orchestrate`, `GET /agents/portal[.html]`.

**Resources:** `agents://overview`, `agents://catalog`, `agents://products`, `agents://runs`,
`agents://smart-actions`, `agent://{key}`.
**Prompt:** `agentic_workspace_brief`.

```powershell
# the prioritised morning brief (deals, deadlines, renewals, arrears, warm leads)
curl "http://127.0.0.1:8000/agents/smart-actions"

# run the conversational buyer agent against the live catalogue
curl -X POST "http://127.0.0.1:8000/agents/run" -H "Content-Type: application/json" -d '{"agent_key":"conversational_buyer_agent","objective":"find a 3-bed house","text":"3 crore, 3 bed, Lahore, 35 min commute"}'

# pause at the approval gate, then approve
curl -X POST "http://127.0.0.1:8000/agents/run" -H "Content-Type: application/json" -d '{"agent_key":"transaction_agent","objective":"review a deal","approve":false}'
```

### Transactions — the deal-to-close lifecycle

Offers, contract terms, milestone/deadline checklists, e-signatures, then on close a
commission + VAT computation whose **balanced journal entry** is posted to the ledger and
whose platform/listing-agent/selling-agent payouts are recorded.

**MCP tools:** `transaction_stages`, `transaction_create`, `transactions_list`,
`transaction_get`, `transaction_update`, `transaction_milestone_add`,
`transaction_milestone_complete`, `transaction_extract_terms`, `transaction_offer_add`,
`transaction_offer_respond`, `transaction_signature_add`, `transaction_signatures`,
`transaction_progress`, `transaction_deadlines`, `transaction_close`, `transaction_report`.

**REST:** `GET /transactions/stages`, `POST /transactions`, `GET /transactions`,
`GET /transactions/{tx_id}`, `PUT /transactions/{tx_id}`, `POST /transactions/{tx_id}/milestones`,
`POST /transactions/{tx_id}/milestones/{key}/complete`, `POST /transactions/terms/extract`,
`POST /transactions/{tx_id}/offers`, `POST /transactions/offers/{offer_id}/respond`,
`POST /transactions/{tx_id}/signatures`, `GET /transactions/{tx_id}/signatures`,
`GET /transactions/{tx_id}/progress`, `GET /transactions/deadlines`,
`POST /transactions/{tx_id}/close`, `POST /transactions/{tx_id}/report`.

**Resources:** `transactions://all`, `transactions://deadlines`, `transaction://{tx_id}`.
**Prompt:** `transaction_close_prompt`.

```powershell
curl -X POST "http://127.0.0.1:8000/transactions" -H "Content-Type: application/json" -d '{"transaction_type":"sale","price":30000000,"property_title":"10 Marla House"}'
curl -X POST "http://127.0.0.1:8000/transactions/{tx_id}/close" -H "Content-Type: application/json" -d '{}'
```

### Buyer / seller / investor intelligence

**MCP tools:** `buyer_parse_requirement`, `buyer_recommend`, `buyer_anomaly_scan`,
`buyer_affordability`, `buyer_report`, `seller_cma`, `seller_net_proceeds`,
`seller_marketing_assets`, `seller_report`, `investment_underwrite`, `investment_screen`,
`investment_portfolio_alerts`, `investment_report`.

**REST:** `POST /intelligence/buyer/parse`, `POST /intelligence/buyer/recommend`,
`GET /intelligence/buyer/anomalies`, `GET /intelligence/buyer/affordability`,
`POST /intelligence/buyer/report`, `GET /intelligence/seller/cma/{property_id}`,
`GET /intelligence/seller/net-proceeds`, `GET /intelligence/seller/marketing/{property_id}`,
`POST /intelligence/seller/report/{property_id}`, `POST /intelligence/investment/underwrite`,
`GET /intelligence/investment/screen`, `POST /intelligence/investment/alerts`,
`POST /intelligence/investment/report`.

**Resources:** `intelligence://anomalies`, `intelligence://screener`.
**Prompts:** `conversational_buyer_brief`, `seller_pricing_listing`, `investment_screener_prompt`.

```powershell
curl -X POST "http://127.0.0.1:8000/intelligence/buyer/recommend" -H "Content-Type: application/json" -d '{"text":"house in Lahore, budget 5 crore, good schools"}'
curl "http://127.0.0.1:8000/intelligence/investment/screen?min_cap_rate=0.02"
```

### Autonomous leasing

**MCP tools:** `leasing_units`, `leasing_unit`, `leasing_unit_create`, `leasing_rent_floor`,
`leasing_inquiry`, `leasing_inquiries`, `leasing_screen_application`, `leasing_renewals`,
`leasing_collection`, `leasing_funnel`, `leasing_portal`.

**REST:** `GET/POST /leasing/units`, `GET /leasing/units/{unit_id}`, `GET /leasing/rent-floor`,
`POST /leasing/inquiries`, `GET /leasing/inquiries`, `POST /leasing/apply`,
`GET /leasing/renewals`, `GET /leasing/collection`, `GET /leasing/funnel`,
`GET /leasing/portal[.html]`.

**Resources:** `leasing://units`, `leasing://funnel`, `leasing://inquiries`.

```powershell
curl "http://127.0.0.1:8000/leasing/rent-floor?monthly_holding_cost=70000"
curl -X POST "http://127.0.0.1:8000/leasing/inquiries" -H "Content-Type: application/json" -d '{"message":"Is it still available? What is the rent?"}'
```

### AI marketing conductor

**MCP tools:** `marketing_channels`, `marketing_routes`, `marketing_route_add`,
`marketing_qualify`, `marketing_route_lead`, `marketing_reengagement`,
`marketing_generate_content`, `marketing_content_assets`, `marketing_content_approve`,
`marketing_campaign_plan`, `marketing_funnel`, `marketing_portal`.

**REST:** `GET /marketing/channels`, `GET/POST /marketing/routes`,
`POST /marketing/qualify/{lead_id}`, `POST /marketing/route/{lead_id}`,
`GET /marketing/reengagement`, `POST/GET /marketing/content`,
`POST /marketing/content/{asset_id}/approve`, `POST /marketing/campaigns`,
`GET /marketing/funnel`, `GET /marketing/portal[.html]`.

**Resources:** `marketing://routes`, `marketing://funnel`, `marketing://content`.

```powershell
curl -X POST "http://127.0.0.1:8000/marketing/qualify/{lead_id}"
curl -X POST "http://127.0.0.1:8000/marketing/campaigns" -H "Content-Type: application/json" -d '{"objective":"sell 10 units","budget":300000,"channels":["whatsapp","website"]}'
```

### Commercialization — products, pricing, metering & payouts

**MCP tools:** `commercial_products`, `commercial_product`, `commercial_plans`,
`commercial_plan`, `commercial_pricing_matrix`, `commercial_recommend_package`,
`commercial_subscribe`, `commercial_subscriptions`, `commercial_meter_usage`,
`commercial_usage`, `commercial_bill`, `commercial_revenue_share`,
`commercial_record_payout`, `commercial_payouts`, `commercial_gtm`, `commercial_portal`.

**REST:** `GET /commercial/products`, `GET /commercial/products/{key}`,
`GET /commercial/plans`, `GET /commercial/plans/{key}`, `GET /commercial/pricing`,
`POST /commercial/recommend`, `POST /commercial/subscribe`, `GET /commercial/subscriptions`,
`POST /commercial/meter`, `GET /commercial/usage/{account}`, `GET /commercial/bill/{account}`,
`POST /commercial/revenue-share`, `POST/GET /commercial/payouts`, `GET /commercial/gtm`,
`GET /commercial/portal[.html]`.

**Resources:** `commercial://products`, `commercial://plans`, `commercial://pricing`,
`commercial://subscriptions`, `commercial://gtm`.

```powershell
# hybrid-pricing matrix + the GTM playbook
curl "http://127.0.0.1:8000/commercial/pricing"
# recommend a plan and estimate the monthly bill
curl -X POST "http://127.0.0.1:8000/commercial/recommend" -H "Content-Type: application/json" -d '{"segment":"broker","seats":3,"expected_calls":3000}'
```

### Product surfaces — MCP for Brokers & Property Intelligence

The two P0 products **MCP for Brokers** and the **Property Intelligence MCP Server** expose
the roadmap's explicitly-named tools as thin, productised front doors over the same engines
(no duplicated logic). They are the pay-per-call surface an external AI client
(Claude / ChatGPT / Cursor) uses; call volume is metered by `commercial`.

**MCP tools:** `search_contacts`, `get_commission_projection`, `analyze_property_gis`,
`get_gis_score`, `get_accounting_snapshot`, `get_market_intelligence`,
`score_seller_intent`, `create_listing_draft`.

**REST:** `GET /broker/contacts`, `GET /broker/commission-projection`,
`GET /broker/property-gis`, `GET /broker/listing-draft/{property_id}`,
`GET /property-intelligence/gis-score`,
`GET /property-intelligence/accounting-snapshot/{property_id}`,
`GET /property-intelligence/market-intelligence`,
`GET /property-intelligence/seller-intent/{contact_id}`.

**Resources:** `broker://contacts`, `broker://commission-projection`,
`property-intelligence://market`, `property-intelligence://gis/{property_id}`.

```powershell
# the broker's "who should I call next" list, scored by move-likelihood
curl "http://127.0.0.1:8000/broker/contacts?lifecycle=hot&min_intent_score=40"
# realised + weighted-pipeline commission from the live deal pipeline
curl "http://127.0.0.1:8000/broker/commission-projection"
# a full listing kit (headline, description, social posts, e-mail, video script)
curl "http://127.0.0.1:8000/broker/listing-draft/{property_id}?tone=luxury"
# the Property-Intelligence GIS score for an address
curl "http://127.0.0.1:8000/property-intelligence/gis-score?address=Lahore"
```

## Quick examples

MCP tool call:

```python
from mcp import Client
import server

async with Client(server.mcp) as client:
    result = await client.call_tool("search_properties", {"city": "Lahore", "max_price": 50_000_000})
```

REST:

```powershell
curl "http://127.0.0.1:8000/search?city=Lahore&max_price=50000000"
curl "http://127.0.0.1:8000/crm/dashboard"
curl "http://127.0.0.1:8000/units/convert?value=10&from_unit=marla&to_unit=sqft"
curl "http://127.0.0.1:8000/gis/base-maps"
curl "http://127.0.0.1:8000/gis/master-plans"
curl "http://127.0.0.1:8000/gis/properties-in-bounds?south=31.40&west=74.20&north=31.55&east=74.40"
curl "http://127.0.0.1:8000/gis/analysis/scheme/{scheme_id}/cost-development"
curl "http://127.0.0.1:8000/gis/analysis/scheme/{scheme_id}/forecast?years=5"
curl "http://127.0.0.1:8000/news?city=Lahore"
curl "http://127.0.0.1:8000/news/impact?city=Lahore"
curl "http://127.0.0.1:8000/i18n/languages"
curl "http://127.0.0.1:8000/i18n/strings/ur"
curl "http://127.0.0.1:8000/ui/themes"
curl "http://127.0.0.1:8000/accounting/dashboard"
curl "http://127.0.0.1:8000/accounting/trial-balance"
curl "http://127.0.0.1:8000/accounting/rent-roll"
curl "http://127.0.0.1:8000/finance/portfolio-roi"
curl "http://127.0.0.1:8000/finance/mortgage?principal=8000000"
curl "http://127.0.0.1:8000/poi/nearby?latitude=31.4504&longitude=74.2810&radius_km=3"
curl "http://127.0.0.1:8000/aoi"
curl "http://127.0.0.1:8000/portal/health"
curl "http://127.0.0.1:8000/portal/search?query=lahore"
curl "http://127.0.0.1:8000/construction/overview"
curl "http://127.0.0.1:8000/construction/techniques"
curl "http://127.0.0.1:8000/maintenance/overview"
curl "http://127.0.0.1:8000/maintenance/defects?severity=high"
curl "http://127.0.0.1:8000/agents/overview"
curl "http://127.0.0.1:8000/agents/smart-actions"
curl "http://127.0.0.1:8000/transactions/stages"
curl "http://127.0.0.1:8000/intelligence/buyer/anomalies"
curl "http://127.0.0.1:8000/leasing/funnel"
curl "http://127.0.0.1:8000/marketing/funnel"
curl "http://127.0.0.1:8000/commercial/products"
curl "http://127.0.0.1:8000/broker/contacts?lifecycle=hot"
curl "http://127.0.0.1:8000/broker/commission-projection"
curl "http://127.0.0.1:8000/property-intelligence/gis-score?address=Lahore"
curl "http://127.0.0.1:8000/property-intelligence/market-intelligence?region=Lahore"
```

Open a scheme's interactive map (base-map switcher + overlays) in a browser:

```powershell
# replace {scheme_id} — list schemes first with: curl http://127.0.0.1:8000/schemes
start "http://127.0.0.1:8000/gis/map/scheme/{scheme_id}"
```

Download a KML to view the same master plan in **Google Earth**:

```powershell
curl -o scheme.kml "http://127.0.0.1:8000/gis/export/kml/scheme/{scheme_id}"
```

Open the full investment-outlook report (cost/development, predictions, news ticker):

```powershell
start "http://127.0.0.1:8000/gis/outlook/scheme/{scheme_id}"
start "http://127.0.0.1:8000/news/ticker.html?city=Lahore"
```

Same report in **Urdu**, dark theme, with the language read from the request header:

```powershell
start "http://127.0.0.1:8000/gis/outlook/scheme/{scheme_id}?lang=ur&theme=dark"
curl -H "Accept-Language: ur" "http://127.0.0.1:8000/gis/report/scheme/{scheme_id}"
```

Open an area-of-interest report (analysis + POI + outlook + ticker) and its map:

```powershell
# replace {aoi_id} — list areas first with: curl http://127.0.0.1:8000/aoi
start "http://127.0.0.1:8000/aoi/{aoi_id}/report"
start "http://127.0.0.1:8000/aoi/{aoi_id}/map"
```

## Notes

* Storage is **in-memory** for now (seeded on startup); a PostgreSQL + PostGIS
  backend is the planned next step (`DatabaseConfig` is the seam).
* The MCP HTTP endpoint has DNS-rebinding protection, so send a `Host` of
  `127.0.0.1`/`localhost` (any real client does).
* OTPs are **not** delivered anywhere: they are recorded in the in-memory outbox and,
  while `PORTAL_AUTH_EXPOSE_OTP` is on (the default), echoed back as `dev_otp`.
  Set `PORTAL_AUTH_EXPOSE_OTP=0` to hide them, and swap in a real SMS/e-mail provider by
  replacing `auth._deliver`.
* Language coverage is intentionally partial: unmapped strings stay in English. Add a
  phrase to `gis.TRANSLATIONS["ur"]` to translate it, or a new entry to
  `gis.SUPPORTED_LANGUAGES` to add a language.
