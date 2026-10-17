# REST endpoint reference

Auto-generated from the FastAPI app — **629 routes** across **37 tags**. Every route calls the same function the MCP tool of the same name calls, so behaviour can never drift.

| Tag | Routes |
| --- | --- |
| [messaging](#messaging) | 71 |
| [tools](#tools) | 70 |
| [pmo](#pmo) | 61 |
| [accounting](#accounting) | 32 |
| [maintenance](#maintenance) | 28 |
| [crm](#crm) | 25 |
| [construction](#construction) | 24 |
| [gis](#gis) | 24 |
| [gis-analysis](#gis-analysis) | 18 |
| [auth](#auth) | 17 |
| [commercial](#commercial) | 17 |
| [properties](#properties) | 17 |
| [roles](#roles) | 16 |
| [transactions](#transactions) | 16 |
| [agents](#agents) | 15 |
| [content](#content) | 14 |
| [ads](#ads) | 13 |
| [intelligence](#intelligence) | 13 |
| [marketing](#marketing) | 13 |
| [poi](#poi) | 13 |
| [leasing](#leasing) | 12 |
| [portal](#portal) | 12 |
| [aoi](#aoi) | 11 |
| [hierarchy](#hierarchy) | 10 |
| [big-projects](#big-projects) | 9 |
| [finance](#finance) | 8 |
| [routing](#routing) | 8 |
| [ai](#ai) | 7 |
| [news](#news) | 6 |
| [other](#other) | 5 |
| [broker](#broker) | 4 |
| [images](#images) | 4 |
| [memory](#memory) | 4 |
| [property-intelligence](#property-intelligence) | 4 |
| [system](#system) | 4 |
| [ui](#ui) | 3 |
| [units](#units) | 1 |

## accounting

32 routes.

| Method(s) | Path | Purpose |
| --- | --- | --- |
| GET | `/accounting/accounts` | Chart of accounts with live balances. |
| POST | `/accounting/accounts` | Add a ledger account. |
| PUT | `/accounting/accounts/{code}` | Rename / reclassify / deactivate an account. |
| GET | `/accounting/accounts/{code}/balance` | Debit/credit movement and signed balance of one account. |
| GET | `/accounting/aging` | Receivable/payable ageing buckets. |
| GET | `/accounting/balance-sheet` | Balance sheet at a date. |
| POST | `/accounting/budgets` | Create a budget. |
| GET | `/accounting/budgets` | List budgets. |
| GET | `/accounting/budgets/{budget_id}/variance` | Budget vs actual variance. |
| GET | `/accounting/cash-flow` | Cash-flow statement (operating / investing / financing). |
| GET | `/accounting/chart` | Full chart of accounts with balances (all types). |
| GET | `/accounting/dashboard` | Finance dashboard snapshot. |
| POST | `/accounting/expenses` | Capture an expense. |
| GET | `/accounting/info` | Accounting configuration, allowed values and record counts. |
| POST | `/accounting/invoices` | Create a receivable or payable invoice. |
| GET | `/accounting/invoices` | List invoices with balances and overdue flags. |
| GET | `/accounting/invoices/{invoice_id}` | Fetch one invoice with its payments. |
| POST | `/accounting/invoices/{invoice_id}/post` | Post an invoice to the ledger. |
| POST | `/accounting/journal` | Post a balanced double-entry journal entry. |
| GET | `/accounting/journal` | List journal entries. |
| GET | `/accounting/journal/{entry_id}` | Fetch one journal entry. |
| POST | `/accounting/journal/{entry_id}/void` | Void a journal entry (``{"reason": "..."}`` optional). |
| POST | `/accounting/leases` | Create a lease. |
| GET | `/accounting/leases` | List leases. |
| GET | `/accounting/ledger/{account_code}` | General ledger (running balance) for one account. |
| POST | `/accounting/payments` | Record a receipt or disbursement and allocate it to an invoice. |
| GET | `/accounting/profit-and-loss` | Profit & loss, optionally scoped to a property / scheme / city. |
| GET | `/accounting/properties/{property_id}/performance` | Property-level P&L, rent roll and yields. |
| GET | `/accounting/ratios` | Liquidity, leverage and profitability ratios. |
| POST | `/accounting/rent-invoices` | Raise this period's rent invoices for every due lease. |
| GET | `/accounting/rent-roll` | Rent roll of active leases. |
| GET | `/accounting/trial-balance` | Trial balance at a date. |

## ads

13 routes.

| Method(s) | Path | Purpose |
| --- | --- | --- |
| GET | `/ads` | List advertisement creatives. |
| POST | `/ads` | Create an advertisement creative. |
| GET | `/ads/active` | Live, in-window, on-target creatives (weighted rotation). |
| GET | `/ads/categories` | Advertisement categories. |
| GET | `/ads/performance` | Impression / click / CTR performance for one ad or the whole book. |
| GET | `/ads/preview` | HTML preview of an advertisement slot. |
| GET | `/ads/report` | Printable advertising report (all slots + delivery performance). |
| GET | `/ads/section` | A ready-to-render advertisement section. |
| GET | `/ads/slots` | Advertisement slots. |
| GET | `/ads/{ad_id}` | Fetch one advertisement. |
| PUT | `/ads/{ad_id}` | Update an advertisement. |
| DELETE | `/ads/{ad_id}` | Delete an advertisement. |
| POST | `/ads/{ad_id}/track` | Record an impression / click / spend event. |

## agents

15 routes.

| Method(s) | Path | Purpose |
| --- | --- | --- |
| GET | `/agents/catalog` | The agent catalogue (product agents plus specialist sub-agents). |
| GET | `/agents/move-likelihood/{lead_id}` | Score a CRM lead's likelihood of moving (0–100). |
| POST | `/agents/orchestrate` | Plan a multi-agent hand-off chain for a shared objective. |
| GET | `/agents/overview` | Counts, products, autonomy mix and run activity across the Agentic OS. |
| POST | `/agents/plan` | Plan (but do not execute) an agent run. |
| GET | `/agents/portal` | The Agentic OS page (HTML). |
| GET | `/agents/portal.html` | Alias of ``/agents/portal`` that always serves HTML. |
| GET | `/agents/products` | The eight roadmap products and their agent modules. |
| POST | `/agents/run` | Execute an agent run against the live portal. |
| GET | `/agents/runs` | Recorded agent runs (the audit trail). |
| GET | `/agents/runs/{run_id}` | One agent run with its steps, outputs and approvals. |
| POST | `/agents/runs/{run_id}/approve` | Approve a paused agent run (human-in-the-loop gate). |
| GET | `/agents/seller-intent` | Score how likely a contact is to sell (0–100). |
| GET | `/agents/smart-actions` | The prioritised Smart Actions morning brief. |
| GET | `/agents/{key}` | One agent's full definition by key. |

## ai

7 routes.

| Method(s) | Path | Purpose |
| --- | --- | --- |
| GET | `/ai/capabilities` | What the assistant can use: the OpenAI chat model and OpenAI voice (no secrets). |
| POST | `/ai/realtime/session` | Start a live voice conversation (OpenAI Realtime API). |
| POST | `/ai/speak` | Text-to-speech for voice-note replies (OpenAI ``OPENAI_TTS_MODEL`` with ``OPENAI_VOICE`` / |
| GET | `/ai/tools` | The assistant's tools in Chat Completions format (the same ones the live agent gets). |
| POST | `/ai/transcribe` | Speech-to-text for voice notes (OpenAI ``OPENAI_TRANSCRIBE_MODEL``; Urdu, English or mixed). |
| GET | `/rag/search` |  |
| POST | `/rag/search` |  |

## aoi

11 routes.

| Method(s) | Path | Purpose |
| --- | --- | --- |
| POST | `/aoi` | Save an area of interest. |
| GET | `/aoi` | List saved areas of interest. |
| POST | `/aoi/compare` | Compare areas of interest side by side. |
| GET | `/aoi/{aoi_id}` | Fetch one area of interest. |
| PUT | `/aoi/{aoi_id}` | Update an area of interest. |
| DELETE | `/aoi/{aoi_id}` | Delete an area of interest. |
| GET | `/aoi/{aoi_id}/analyze` | Full analytics for an area of interest. |
| GET | `/aoi/{aoi_id}/map` | HTML map of an area of interest. |
| GET | `/aoi/{aoi_id}/report` | Printable HTML report for an area of interest. |
| GET | `/aoi/{aoi_id}/stats` | Quick statistics for an area of interest. |
| GET | `/aoi/{aoi_id}/watch` | News watch for an area of interest. |

## auth

17 routes.

| Method(s) | Path | Purpose |
| --- | --- | --- |
| GET | `/auth/config` | OTP/session/password policy plus live counters. |
| GET | `/auth/events` | Authentication audit trail. |
| POST | `/auth/login` | Password login. Returns `401` for bad credentials and `403` for unverified accounts. |
| POST | `/auth/logout` | Revoke the bearer token. |
| GET | `/auth/me` | Return the authenticated account (Bearer token required). |
| GET | `/auth/notifications` | The simulated SMS/e-mail outbox. |
| POST | `/auth/otp/request` | Start a passwordless login by sending an OTP. |
| POST | `/auth/otp/verify` | Complete a passwordless login with the OTP. |
| GET | `/auth/otps` | Dev view of outstanding verification codes (plaintext only when exposed). |
| POST | `/auth/password/reset` | Reset a password with the reset code (revokes all sessions). |
| POST | `/auth/password/reset-request` | Send a password-reset code. |
| POST | `/auth/password/set` | Set or change the password of the signed-in user (Bearer token required). |
| POST | `/auth/refresh` | Exchange a valid token for a fresh one. |
| POST | `/auth/resend-otp` | Re-send a verification code (cooldown + hourly cap apply). |
| POST | `/auth/signup` | Register with an email and/or mobile number. The account stays *pending* |
| GET | `/auth/users` | List accounts (Bearer token required). |
| POST | `/auth/verify-otp` | Verify a signup/login/reset OTP. Activating a signup returns a bearer token. |

## big-projects

9 routes.

| Method(s) | Path | Purpose |
| --- | --- | --- |
| GET | `/bigprojects` |  |
| POST | `/bigprojects` | Add a big project (mall / tower / mixed-use / compound / plaza / office complex). |
| GET | `/bigprojects/{project_id}` |  |
| PUT | `/bigprojects/{project_id}` | Update a big project. |
| DELETE | `/bigprojects/{project_id}` | Delete a big project. |
| POST | `/bigprojects/{project_id}/amenities` | Add an amenity to a big project (``{"amenity": "..."}``). |
| POST | `/bigprojects/{project_id}/floor-plans` | Attach a floor plan (``{"floor_plan_url": "..."}``). |
| POST | `/bigprojects/{project_id}/maps` | Attach a map image (``{"map_url": "..."}``). |
| POST | `/bigprojects/{project_id}/multimedia` | Attach multimedia (``{"media_type": "video", "url": "..."}``). |

## broker

4 routes.

| Method(s) | Path | Purpose |
| --- | --- | --- |
| GET | `/broker/commission-projection` | Realised + weighted-pipeline commission projection from the live deal pipeline. |
| GET | `/broker/contacts` | CRM contacts with live move-likelihood intent scoring (product: MCP for Brokers). |
| GET | `/broker/listing-draft/{property_id}` | Draft a complete listing kit (headline, description, social posts, e-mail, video). |
| GET | `/broker/property-gis` | GIS-enhanced property analysis (amenities, schools, safety, commute). |

## commercial

17 routes.

| Method(s) | Path | Purpose |
| --- | --- | --- |
| GET | `/commercial/bill/{account}` | A usage-based billing statement for an account. |
| GET | `/commercial/gtm` | The go-to-market playbook. |
| POST | `/commercial/meter` | Record a metered usage event for an account. |
| POST | `/commercial/payouts` | Record a payee payout against a transaction commission. |
| GET | `/commercial/payouts` | Recorded payouts. |
| GET | `/commercial/plans` | Subscription / usage plans. |
| GET | `/commercial/plans/{key}` | One pricing plan by key. |
| GET | `/commercial/portal` | The Commercialization wing page (HTML). |
| GET | `/commercial/portal.html` | Alias of ``/commercial/portal`` that always serves HTML. |
| GET | `/commercial/pricing` | The hybrid-pricing matrix and GTM playbook. |
| GET | `/commercial/products` | The commercial product catalogue. |
| GET | `/commercial/products/{key}` | One commercial product by key. |
| POST | `/commercial/recommend` | Recommend the best-fit plan for a segment and estimate the monthly bill. |
| POST | `/commercial/revenue-share` | Split a commission into platform and partner shares. |
| POST | `/commercial/subscribe` | Create a subscription for an account on a plan. |
| GET | `/commercial/subscriptions` | Active subscriptions. |
| GET | `/commercial/usage/{account}` | Usage summary for an account. |

## construction

24 routes.

| Method(s) | Path | Purpose |
| --- | --- | --- |
| GET | `/construction/advisory` | Recommend a technique, foundation and guidelines for a site. |
| GET | `/construction/approvals` | NOC / approval workflow for a project type. |
| GET | `/construction/compare` | Compare competing construction techniques. |
| GET | `/construction/element-rates` | BOQ element unit rates for rate analysis. |
| POST | `/construction/estimate` | Parameterised construction-cost estimate. |
| POST | `/construction/estimates` | Compute and persist a construction estimate. |
| GET | `/construction/estimates` | Saved construction estimates. |
| GET | `/construction/estimates/{estimate_id}` | One saved construction estimate. |
| GET | `/construction/guidelines` | Building codes, byelaws and guidelines. |
| GET | `/construction/hse` | Health, safety & environment rules. |
| GET | `/construction/impact` | Impact of construction quality on value, rent and payback. |
| GET | `/construction/materials` | Building-material catalogue with unit rates. |
| GET | `/construction/materials/{key}` | One building material by key. |
| GET | `/construction/overview` | Counts, categories and configuration for the construction wing. |
| GET | `/construction/portal` | The Construction wing page (HTML). |
| GET | `/construction/portal.html` | Alias of ``/construction/portal`` that always serves HTML. |
| GET | `/construction/qa` | QA inspection checklists by stage. |
| GET | `/construction/rate-analysis` | Rate analysis for one BOQ element. |
| POST | `/construction/report` | Construction cost report (HTML). |
| GET | `/construction/takeoff` | Indicative material take-off. |
| GET | `/construction/techniques` | Catalogue of construction techniques / systems. |
| GET | `/construction/techniques/{key}` | One construction technique by key. |
| GET | `/construction/timeline` | Phase-weighted construction timeline. |
| GET | `/construction/trades` | Construction trades with daily wage rates. |

## content

14 routes.

| Method(s) | Path | Purpose |
| --- | --- | --- |
| GET | `/content/contacts` | The contact directory. |
| POST | `/content/contacts` | Add a contact channel. |
| GET | `/content/history` | The company-history timeline. |
| POST | `/content/history` | Add a company-history entry. |
| GET | `/content/navigation` | The portal navigation menu. |
| GET | `/content/overview` | Counts and breakdowns for pages, history, contacts, stories and ads. |
| GET | `/content/pages` | List portal content pages. |
| POST | `/content/pages` | Create a portal content page. |
| GET | `/content/pages/{key}` | Fetch one content page by key. |
| PUT | `/content/pages/{key}` | Update a portal content page. |
| DELETE | `/content/pages/{key}` | Delete a portal content page. |
| GET | `/content/site` | The complete portal site payload (nav, blocks, content, resolved ads). |
| GET | `/content/stories` | Success stories, case studies and testimonials. |
| POST | `/content/stories` | Publish a success story. |

## crm

25 routes.

| Method(s) | Path | Purpose |
| --- | --- | --- |
| GET | `/crm/agents` |  |
| POST | `/crm/agents` | Add a sales agent. |
| GET | `/crm/agents/{agent_id}` | Fetch one agent with their pipeline. |
| PUT | `/crm/agents/{agent_id}` | Update an agent. |
| GET | `/crm/appointments` |  |
| POST | `/crm/appointments` | Schedule an appointment. |
| GET | `/crm/customers` |  |
| POST | `/crm/customers` | Add a customer. |
| GET | `/crm/customers/{customer_id}` | Fetch one customer with their deals and interactions. |
| GET | `/crm/dashboard` |  |
| GET | `/crm/deals` |  |
| POST | `/crm/deals` |  |
| PUT | `/crm/deals/{deal_id}/stage` | Move a deal to a new stage (and/or probability). |
| GET | `/crm/interactions` | List interactions, optionally filtered by related entity. |
| POST | `/crm/interactions` | Log an interaction against a lead / customer / deal. |
| GET | `/crm/leads` |  |
| POST | `/crm/leads` |  |
| GET | `/crm/leads/{lead_id}` |  |
| PUT | `/crm/leads/{lead_id}` | Update a lead (status, score, budget, assignment). |
| POST | `/crm/leads/{lead_id}/assign` | Assign a lead to an agent (``{"agent_id": "..."}``). |
| POST | `/crm/leads/{lead_id}/convert` |  |
| GET | `/crm/pipeline` |  |
| GET | `/crm/tasks` |  |
| POST | `/crm/tasks` |  |
| PUT | `/crm/tasks/{task_id}/complete` | Complete (or otherwise update the status of) a task. |

## finance

8 routes.

| Method(s) | Path | Purpose |
| --- | --- | --- |
| GET | `/finance/cap-rate` | Capitalisation rate from NOI and value. |
| GET | `/finance/cash-on-cash` | Cash-on-cash return. |
| POST | `/finance/investment-metrics` | NPV / IRR / payback / PI / equity multiple for a cash-flow series. |
| GET | `/finance/mortgage` | Amortising mortgage: payment, total interest and schedule. |
| GET | `/finance/portfolio-roi` | Portfolio-level leveraged ROI. |
| POST | `/finance/property-roi` | Property ROI: yields, appreciation, leverage, IRR and exit proceeds. |
| GET | `/finance/rental-yield/{property_id}` | Gross/net rental yield and cap rate for a property. |
| POST | `/finance/roi` | Leveraged ROI analysis with scenarios. |

## gis

24 routes.

| Method(s) | Path | Purpose |
| --- | --- | --- |
| GET | `/distance` | Great-circle distance between two points (km). |
| GET | `/gis/area` | Polygon area. `coordinates` is JSON: [[lat,lon], ...]. |
| GET | `/gis/base-maps` |  |
| GET | `/gis/base-maps/{base_map_id}` |  |
| GET | `/gis/bearing` |  |
| POST | `/gis/boundaries` | Add a boundary polygon layer (scheme/society outline). |
| GET | `/gis/centroid` | Polygon centroid. `coordinates` is JSON: [[lat,lon], ...]. |
| GET | `/gis/destination` | Project a point a given bearing/distance (destination point). |
| GET | `/gis/distance-matrix` | Distances from a point to properties. `property_ids` is comma-separated. |
| GET | `/gis/export/geojson/{entity_type}/{entity_id}` |  |
| GET | `/gis/export/kml/{entity_type}/{entity_id}` |  |
| GET | `/gis/layers` |  |
| POST | `/gis/layers` |  |
| GET | `/gis/layers/{layer_id}` |  |
| PUT | `/gis/layers/{layer_id}` |  |
| DELETE | `/gis/layers/{layer_id}` |  |
| GET | `/gis/map` | Interactive Leaflet map centred on a point (all base maps available in the switcher). |
| GET | `/gis/map/{entity_type}/{entity_id}` | Interactive Leaflet map with a base-map switcher and the entity's overlays. |
| GET | `/gis/master-plans` |  |
| POST | `/gis/master-plans` |  |
| GET | `/gis/point-in-layer` | Test whether a point falls inside a layer's polygons. |
| GET | `/gis/properties-in-bounds` |  |
| POST | `/gis/properties-in-polygon` |  |
| POST | `/gis/zones` | Add a zone layer (residential / commercial / amenity). |

## gis-analysis

18 routes.

| Method(s) | Path | Purpose |
| --- | --- | --- |
| GET | `/gis/analysis/assumptions` |  |
| GET | `/gis/analysis/{entity_type}/{entity_id}` |  |
| GET | `/gis/analysis/{entity_type}/{entity_id}/cost` |  |
| GET | `/gis/analysis/{entity_type}/{entity_id}/cost-development` |  |
| GET | `/gis/analysis/{entity_type}/{entity_id}/economic-impact` |  |
| GET | `/gis/analysis/{entity_type}/{entity_id}/factors` |  |
| GET | `/gis/analysis/{entity_type}/{entity_id}/forecast` |  |
| GET | `/gis/analysis/{entity_type}/{entity_id}/population` |  |
| GET | `/gis/analysis/{entity_type}/{entity_id}/scenarios` |  |
| POST | `/gis/buffer` |  |
| GET | `/gis/buffer/point` |  |
| POST | `/gis/buffers` |  |
| GET | `/gis/features/{scope_type}/{scope_id}` |  |
| GET | `/gis/outlook/{entity_type}/{entity_id}` | Full investment-outlook report: cost/development, predictions, risks and a news ticker. |
| POST | `/gis/polygon-analysis` |  |
| GET | `/gis/report/{entity_type}/{entity_id}` | Printable HTML analysis report (area, valuation, population, cost, economics). |
| GET | `/gis/ring-analysis` | Concentric-ring accessibility analysis. `radii_km` is comma-separated. |
| GET | `/gis/thematic/{scope_type}/{scope_id}` | Choropleth (thematic) map HTML for a metric across a city's schemes or a scheme's blocks. |

## hierarchy

10 routes.

| Method(s) | Path | Purpose |
| --- | --- | --- |
| GET | `/blocks` | List blocks / zones / areas, optionally filtered by scheme. |
| POST | `/blocks` | Add a block / zone / area to a scheme. |
| GET | `/cities` |  |
| POST | `/cities` | Add a city. |
| GET | `/cities/{city}` | Full details for a city (by id or name): schemes, properties and value. |
| GET | `/cities/{city}/coordinates` | Latitude/longitude of a city (by id or name). |
| GET | `/cities/{city}/insights` |  |
| GET | `/hierarchy` |  |
| GET | `/schemes` |  |
| POST | `/schemes` | Add a housing scheme / society. |

## images

4 routes.

| Method(s) | Path | Purpose |
| --- | --- | --- |
| POST | `/images` | Store an image URL against an entity. |
| GET | `/images/{entity_type}/{entity_id}` | List images stored for an entity. |
| POST | `/images/{entity_type}/{entity_id}/primary` | Mark one stored image as the primary/cover image (``{"image_index": 0}``). |
| DELETE | `/images/{entity_type}/{entity_id}/{image_index}` | Delete a stored image by index. |

## intelligence

13 routes.

| Method(s) | Path | Purpose |
| --- | --- | --- |
| GET | `/intelligence/buyer/affordability` | Monthly payment, tax, holding costs and an affordability verdict. |
| GET | `/intelligence/buyer/anomalies` | Z-score the market for bargains and overpriced listings. |
| POST | `/intelligence/buyer/parse` | Parse a natural-language buyer brief into a structured requirement. |
| POST | `/intelligence/buyer/recommend` | Rank live listings against a parsed buyer brief. |
| POST | `/intelligence/buyer/report` | The buyer brief & shortlist (HTML). |
| POST | `/intelligence/investment/alerts` | Proactive investor alerts for a portfolio. |
| POST | `/intelligence/investment/report` | Investment screener report (HTML). |
| GET | `/intelligence/investment/screen` | Screen the live listing book into a risk-adjusted shortlist. |
| POST | `/intelligence/investment/underwrite` | Underwrite a deal: returns, debt, DSCR and a risk-adjusted grade. |
| GET | `/intelligence/seller/cma/{property_id}` | Adjusted-comparable market analysis for a property. |
| GET | `/intelligence/seller/marketing/{property_id}` | Generate a full marketing kit for a listing. |
| GET | `/intelligence/seller/net-proceeds` | A seller's net cash after commission, costs, payoff and capital gains. |
| POST | `/intelligence/seller/report/{property_id}` | Seller pricing & marketing report (HTML). |

## leasing

12 routes.

| Method(s) | Path | Purpose |
| --- | --- | --- |
| POST | `/leasing/apply` | Screen a rental application. |
| GET | `/leasing/collection` | Rent-collection board from the ledger. |
| GET | `/leasing/funnel` | Leasing funnel metrics. |
| POST | `/leasing/inquiries` | Handle a tenant inquiry autonomously. |
| GET | `/leasing/inquiries` | Log of handled leasing inquiries. |
| GET | `/leasing/portal` | The Autonomous Leasing wing page (HTML). |
| GET | `/leasing/portal.html` | Alias of ``/leasing/portal`` that always serves HTML. |
| GET | `/leasing/renewals` | Renewal recommendations for every active lease. |
| GET | `/leasing/rent-floor` | Minimum rent that keeps a unit cash-flow positive. |
| GET | `/leasing/units` | Rental units available to the leasing agent. |
| POST | `/leasing/units` | Register a rental unit. |
| GET | `/leasing/units/{unit_id}` | One rental unit by id. |

## maintenance

28 routes.

| Method(s) | Path | Purpose |
| --- | --- | --- |
| GET | `/maintenance/components` | Maintainable components with service lives and criticality. |
| GET | `/maintenance/components/{key}` | One maintainable component by key. |
| GET | `/maintenance/condition` | Score a building's condition into a band with recommended actions. |
| GET | `/maintenance/defects` | The defect catalogue. |
| GET | `/maintenance/defects/{key}` | One defect by key. |
| GET | `/maintenance/estimate` | Annual maintenance cost estimate with a category breakdown and reserve. |
| GET | `/maintenance/guidelines` | Maintenance best-practice, compliance and safety guidelines. |
| GET | `/maintenance/impact` | How maintenance moves value, rent, yield and occupancy. |
| GET | `/maintenance/inspection` | Inspection checklists by area. |
| GET | `/maintenance/lifecycle` | Multi-year capital-replacement schedule (reserve study). |
| GET | `/maintenance/overview` | Counts, categories and configuration for the maintenance wing. |
| POST | `/maintenance/plans` | Compute and persist a maintenance plan. |
| GET | `/maintenance/plans` | Saved maintenance plans. |
| GET | `/maintenance/plans/{plan_id}` | One saved maintenance plan. |
| GET | `/maintenance/portal` | The Maintenance wing page (HTML). |
| GET | `/maintenance/portal.html` | Alias of ``/maintenance/portal`` that always serves HTML. |
| GET | `/maintenance/repair-estimate` | Estimate the cost to repair a known defect. |
| GET | `/maintenance/repair-or-replace` | Repair-vs-replace decision with a 5-year cost comparison. |
| POST | `/maintenance/report` | Maintenance report (HTML). |
| GET | `/maintenance/reserve` | Annual sinking-fund (reserve) contribution. |
| GET | `/maintenance/schedule` | A periodic preventive-maintenance calendar. |
| GET | `/maintenance/services` | Maintenance services and trades with cost bands. |
| GET | `/maintenance/services/{key}` | One maintenance service by key. |
| GET | `/maintenance/warranty` | Warranty terms by component. |
| POST | `/maintenance/work-orders` | Raise a maintenance work order. |
| GET | `/maintenance/work-orders` | List maintenance work orders. |
| GET | `/maintenance/work-orders/{wo_id}` | One maintenance work order. |
| PUT | `/maintenance/work-orders/{wo_id}` | Update a maintenance work order. |

## marketing

13 routes.

| Method(s) | Path | Purpose |
| --- | --- | --- |
| POST | `/marketing/campaigns` | Plan a multichannel campaign. |
| GET | `/marketing/channels` | Cross-channel lead sources and content kinds. |
| POST | `/marketing/content` | Generate a marketing content asset. |
| GET | `/marketing/content` | Content assets by status. |
| POST | `/marketing/content/{asset_id}/approve` | Human approval gate for a content asset. |
| GET | `/marketing/funnel` | Lead funnel metrics. |
| GET | `/marketing/portal` | The AI Marketing Conductor wing page (HTML). |
| GET | `/marketing/portal.html` | Alias of ``/marketing/portal`` that always serves HTML. |
| POST | `/marketing/qualify/{lead_id}` | Qualify a CRM lead and sync the score back. |
| GET | `/marketing/reengagement` | Dormant / false-negative lead re-engagement candidates. |
| POST | `/marketing/route/{lead_id}` | Route a CRM lead to the best-matching rule. |
| GET | `/marketing/routes` | Lead-routing rules. |
| POST | `/marketing/routes` | Add a lead-routing rule. |

## memory

4 routes.

| Method(s) | Path | Purpose |
| --- | --- | --- |
| GET | `/memory` |  |
| POST | `/memory` |  |
| DELETE | `/memory` | Clear the near cache and long-term memory. |
| GET | `/memory/retrieve` | Read a value from long-term memory or the near cache. |

## messaging

71 routes.

| Method(s) | Path | Purpose |
| --- | --- | --- |
| GET | `/messaging/actions` | List tracked actions. |
| GET | `/messaging/actions/{action_id}` | One tracked action. |
| PUT | `/messaging/actions/{action_id}` | Update an action's status, owner or due date. |
| POST | `/messaging/actions/{action_id}/complete` | Mark an action done and notify its creator. |
| GET | `/messaging/attachment-kinds` | Attachment kinds, accepted extensions and default sensitivity. |
| GET | `/messaging/attachments/resolve/{token}` | Verify a signed attachment link and return the file reference. |
| GET | `/messaging/attachments/{attachment_id}` | Resolve an attachment through a signed token (re-checks membership + expiry). |
| GET | `/messaging/attachments/{attachment_id}/link` | Mint a signed, expiring, permission-checked download link. |
| GET | `/messaging/audit` | The messaging audit trail. |
| GET | `/messaging/categories` | Notification categories with delivery channels and urgency. |
| GET | `/messaging/categories/{category}` | One notification category by key. |
| GET | `/messaging/channels` | Default team channels with purpose and access rules. |
| GET | `/messaging/channels/{channel_key}` | One team channel by key. |
| GET | `/messaging/conversations` | List a user's conversations with unread counts. |
| POST | `/messaging/conversations` | Create a direct / group / channel / property conversation. |
| GET | `/messaging/conversations/{conversation_id}` | One conversation with members, pins, unread count and context. |
| POST | `/messaging/conversations/{conversation_id}/action-items` | Extract (and optionally create) action items from a conversation. |
| GET | `/messaging/conversations/{conversation_id}/actions` | Actions raised inside a conversation. |
| POST | `/messaging/conversations/{conversation_id}/actions` | Turn a message (or conversation) into a tracked action. |
| POST | `/messaging/conversations/{conversation_id}/archive` | Archive or restore a conversation. |
| GET | `/messaging/conversations/{conversation_id}/attachments` | List a conversation's shared files (references, never embedded content). |
| POST | `/messaging/conversations/{conversation_id}/attachments` | Register a file reference for sharing. |
| GET | `/messaging/conversations/{conversation_id}/context` | What a conversation is tied to (property, pins, actions, attachments). |
| GET | `/messaging/conversations/{conversation_id}/digest` | Recent-activity digest for a conversation. |
| GET | `/messaging/conversations/{conversation_id}/members` | Members of a conversation. |
| POST | `/messaging/conversations/{conversation_id}/members` | Add (or re-role) a member. |
| PUT | `/messaging/conversations/{conversation_id}/members/{member_id}` | Update a member's role, mute/pin state or notification level. |
| DELETE | `/messaging/conversations/{conversation_id}/members/{member_id}` | Remove a member (audited access revocation). |
| GET | `/messaging/conversations/{conversation_id}/messages` | Page through a conversation's messages (or one thread). |
| POST | `/messaging/conversations/{conversation_id}/messages` | Post a message. |
| POST | `/messaging/conversations/{conversation_id}/read` | Mark a conversation read up to a sequence number. |
| GET | `/messaging/conversations/{conversation_id}/summary` | Rules-based extractive summary of a conversation. |
| POST | `/messaging/direct` | Find or create the 1-to-1 conversation between two users. |
| POST | `/messaging/dispatch` | Drain the notification queue into the outbox (background-worker seam). |
| GET | `/messaging/messages/{message_id}` | One message with attachments, reactions, receipts and replies. |
| PUT | `/messaging/messages/{message_id}` | Edit a message (author only, within the edit window). |
| DELETE | `/messaging/messages/{message_id}` | Soft-delete a message. |
| POST | `/messaging/messages/{message_id}/pin` | Pin or unpin a message. |
| POST | `/messaging/messages/{message_id}/react` | Toggle an emoji reaction. |
| GET | `/messaging/messages/{message_id}/receipts` | Read receipts for a message. |
| GET | `/messaging/messages/{message_id}/thread` | Threaded replies to a message. |
| POST | `/messaging/notifications/{notification_id}/read` | Mark one notification read. |
| GET | `/messaging/notifications/{user_id}` | A user's notifications with unread count. |
| POST | `/messaging/notifications/{user_id}/read-all` | Mark every notification read for a user. |
| GET | `/messaging/outbox` | Delivered notifications with rendered e-mail/Telegram payloads. |
| GET | `/messaging/overview` | Workspace config, channels, categories, counts and the rollout plan. |
| GET | `/messaging/portal` | The Team Messaging & Notifications page (HTML). |
| GET | `/messaging/portal.html` | Alias of ``/messaging/portal`` that always serves HTML. |
| GET | `/messaging/preferences/{user_id}` | A user's notification preferences, quiet hours, digest and Telegram state. |
| PUT | `/messaging/preferences/{user_id}` | Update notification preferences. |
| POST | `/messaging/presence` | Set a user's presence. |
| POST | `/messaging/presence/heartbeat` | Heartbeat a user's presence. |
| GET | `/messaging/profiles` | Team directory of messaging profiles. |
| POST | `/messaging/property-thread` | Get or create the internal discussion panel for a property. |
| POST | `/messaging/purge` | Apply the retention policy (soft-delete past the window; pinned exempt). |
| GET | `/messaging/reports` | Message reports and their moderation status. |
| POST | `/messaging/reports` | Report a message (spam, abuse, confidential leak, off-topic). |
| POST | `/messaging/reports/{report_id}/moderate` | Resolve a report: dismiss, delete, mute the author or escalate. |
| GET | `/messaging/retention` | Per-conversation retention picture. |
| POST | `/messaging/revoke-access` | Revoke a user's access to every conversation and unlink Telegram. |
| GET | `/messaging/search` | Search messages across every conversation the user may access. |
| GET | `/messaging/statistics` | Aggregate messaging statistics. |
| POST | `/messaging/telegram/alert` | Queue and dispatch a sanitised Telegram alert. |
| POST | `/messaging/telegram/link` | Opt a user in: bind a Telegram chat id and allowed categories. |
| POST | `/messaging/telegram/link-code` | Mint a single-use /start code for linking a Telegram chat. |
| GET | `/messaging/telegram/links` | Every Telegram link. |
| GET | `/messaging/telegram/status/{user_id}` | WhatsApp-style status for the Telegram channel (link state and categories). |
| POST | `/messaging/telegram/unlink` | Unlink a user's Telegram chat. |
| POST | `/messaging/telegram/update` | Process one inbound Telegram bot update. |
| GET | `/messaging/unread-summary/{user_id}` | Combined unread picture for a user. |
| GET | `/messaging/unread/{user_id}` | Unread totals overall and per conversation. |

## news

6 routes.

| Method(s) | Path | Purpose |
| --- | --- | --- |
| GET | `/news` |  |
| POST | `/news` |  |
| GET | `/news/channels` |  |
| GET | `/news/impact` |  |
| GET | `/news/ticker` | Scrolling ticker as an embeddable HTML fragment (text/html). |
| GET | `/news/ticker.html` | Standalone page hosting the ticker (handy for an iframe embed). |

## other

5 routes.

| Method(s) | Path | Purpose |
| --- | --- | --- |
| GET, HEAD | `/docs` |  |
| GET, HEAD | `/docs/oauth2-redirect` |  |
| WEBSOCKET | `/mcp` |  |
| GET, HEAD | `/redoc` |  |
| WEBSOCKET | `/ws/messaging/{conversation_id}` |  |

## pmo

61 routes.

| Method(s) | Path | Purpose |
| --- | --- | --- |
| GET | `/pmo/actions` | List action items. |
| POST | `/pmo/actions/{action_id}/close` | Close a meeting action item. |
| GET | `/pmo/alerts` | Exception-based alerts for one project or the portfolio. |
| POST | `/pmo/allocations` | Assign a resource to a task. |
| GET | `/pmo/capabilities` | The PMO capabilities grouped by category. |
| POST | `/pmo/changes/{change_id}/decide` | Approve or reject a change request. |
| POST | `/pmo/from-estimate/{estimate_id}` | Create a delivery project from a saved Construction-wing estimate. |
| GET | `/pmo/overview` | Counts, breakdowns and configuration for the PMO wing. |
| GET | `/pmo/phase-templates` | Default weighted phase templates by project type. |
| GET | `/pmo/portal` | The Projects & Monitoring (PMO) page (HTML). |
| GET | `/pmo/portal.html` | Alias of ``/pmo/portal`` that always serves HTML. |
| GET | `/pmo/portfolio` | The rolled-up portfolio dashboard. |
| GET | `/pmo/project-types` | The supported project types, statuses and priorities. |
| GET | `/pmo/projects` | List projects with progress and health. |
| POST | `/pmo/projects` | Register a project (optionally seeding its phases and WBS template). |
| GET | `/pmo/projects/{project_id}` | One project by id or code, with its counts. |
| PUT | `/pmo/projects/{project_id}` | Update a project's fields. |
| DELETE | `/pmo/projects/{project_id}` | Delete a project and everything that belongs to it. |
| GET | `/pmo/projects/{project_id}/actions` | List the project's action items. |
| POST | `/pmo/projects/{project_id}/actions` | Add an action item. |
| POST | `/pmo/projects/{project_id}/apply-template` | Seed the project's phases and WBS from its type template. |
| GET | `/pmo/projects/{project_id}/changes` | List the project's change requests. |
| POST | `/pmo/projects/{project_id}/changes` | Raise a change request. |
| GET | `/pmo/projects/{project_id}/cost-status` | The cost-control status. |
| GET | `/pmo/projects/{project_id}/costs` | List the project's cost entries. |
| POST | `/pmo/projects/{project_id}/costs` | Record a cost entry against the project. |
| GET | `/pmo/projects/{project_id}/critical-path` | The critical path for the project. |
| GET | `/pmo/projects/{project_id}/dashboard` | The full project-controls snapshot. |
| GET | `/pmo/projects/{project_id}/earned-value` | The earned-value analysis (PV/EV/AC/SPI/CPI/EAC …). |
| GET | `/pmo/projects/{project_id}/gantt` | Gantt-ready rows for the project. |
| GET | `/pmo/projects/{project_id}/health` | The project's RAG health. |
| GET | `/pmo/projects/{project_id}/inspections` | List the project's inspections and quality index. |
| POST | `/pmo/projects/{project_id}/inspections` | Record an inspection. |
| GET | `/pmo/projects/{project_id}/kpi` | The project's KPI scorecard. |
| GET | `/pmo/projects/{project_id}/milestones` | List the project's milestones. |
| POST | `/pmo/projects/{project_id}/milestones` | Add a milestone. |
| GET | `/pmo/projects/{project_id}/monitoring` | The project-controls monitoring snapshot. |
| GET | `/pmo/projects/{project_id}/phases` | List the project's phases. |
| POST | `/pmo/projects/{project_id}/phases` | Add a phase to the project. |
| GET | `/pmo/projects/{project_id}/progress` | The project's actual vs planned completion, with history. |
| POST | `/pmo/projects/{project_id}/progress` | Record a dated progress update. |
| GET | `/pmo/projects/{project_id}/report` | A full project status report as structured data. |
| GET | `/pmo/projects/{project_id}/risk-matrix` | The probability × impact risk matrix. |
| GET | `/pmo/projects/{project_id}/risks` | List the project's RAID items. |
| POST | `/pmo/projects/{project_id}/risks` | Add a RAID item. |
| GET | `/pmo/projects/{project_id}/s-curve` | The planned-vs-actual S-curve. |
| GET | `/pmo/projects/{project_id}/schedule` | The forward/backward schedule with float and the critical path. |
| GET | `/pmo/projects/{project_id}/site-logs` | List the project's site diary entries. |
| POST | `/pmo/projects/{project_id}/site-logs` | Record a site diary entry. |
| GET | `/pmo/projects/{project_id}/site-report` | A daily site report. |
| GET | `/pmo/projects/{project_id}/tasks` | List the project's tasks with schedule data. |
| POST | `/pmo/projects/{project_id}/tasks` | Add a task. |
| GET | `/pmo/report.html` | A printable project status report (HTML). |
| GET | `/pmo/resource-load` | Planned resource utilisation with over-allocation flags. |
| GET | `/pmo/resources` | List resources. |
| POST | `/pmo/resources` | Register a resource. |
| GET | `/pmo/risks` | List RAID items across the portfolio. |
| PUT | `/pmo/risks/{risk_id}` | Update a RAID item. |
| GET | `/pmo/tasks/{task_id}` | One task by id. |
| PUT | `/pmo/tasks/{task_id}` | Update a task. |
| DELETE | `/pmo/tasks/{task_id}` | Delete a task. |

## poi

13 routes.

| Method(s) | Path | Purpose |
| --- | --- | --- |
| POST | `/poi` | Register a point of interest. |
| GET | `/poi` | List points of interest. |
| GET | `/poi/accessibility` | Distance-decayed liveability score (0-100). |
| GET | `/poi/categories` | POI categories with counts and weights. |
| GET | `/poi/density/{entity_type}/{entity_id}` | POI mix and density inside an entity's footprint. |
| GET | `/poi/map` | HTML map of points of interest. |
| GET | `/poi/nearby` | Points of interest within a radius of a point. |
| GET | `/poi/nearest` | Nearest POI in every category. |
| GET | `/poi/route` | Best route (plus alternatives) between two POIs, fitting the travel mode. |
| POST | `/poi/within-polygon` | Points of interest inside a polygon. |
| GET | `/poi/{poi_id}` | Fetch one point of interest. |
| PUT | `/poi/{poi_id}` | Update a point of interest. |
| DELETE | `/poi/{poi_id}` | Delete a point of interest. |

## portal

12 routes.

| Method(s) | Path | Purpose |
| --- | --- | --- |
| GET | `/portal/audit` | Unified activity trail. |
| GET | `/portal/availability` | Availability breakdown of the listing book. |
| GET | `/portal/catalog` | Inventory of every MCP tool, resource and prompt. |
| GET | `/portal/health` | Liveness snapshot. |
| GET | `/portal/home` | The public portal home page (HTML): content, stories, contacts and ad sections. |
| GET | `/portal/home.html` | Alias of ``/portal/home`` that always serves HTML (for direct browsing). |
| GET | `/portal/market-trends` | Market trends for a city or scheme. |
| GET | `/portal/schema` | JSON schema for a portal model (or the model list). |
| GET | `/portal/search` | Federated search across the whole portal. |
| GET | `/portal/settings` | Read runtime settings. |
| PUT | `/portal/settings` | Update runtime settings (assumptions / forecast / accounting / auth). |
| GET | `/portal/statistics` | Portfolio-wide statistics. |

## properties

17 routes.

| Method(s) | Path | Purpose |
| --- | --- | --- |
| GET | `/me/listings` | Listings published by the signed-in account (Bearer token required). |
| POST | `/me/listings` | Publish a listing owned by the signed-in account. Agents are attributed automatically. |
| PUT | `/me/listings/{property_id}` | Edit one of your listings, e.g. ``{"status": "sold"}``. |
| DELETE | `/me/listings/{property_id}` | Remove one of your listings. |
| POST | `/me/listings/{property_id}/photos` | Attach a photo (JPEG/PNG/WebP, max 5 MB, base64) to one of your listings. |
| GET | `/media/uploads/{name}` | Serve a photo uploaded through ``/me/listings/{id}/photos``. |
| GET | `/nearby` |  |
| GET | `/properties` |  |
| POST | `/properties` |  |
| GET | `/properties/{property_id}` |  |
| PUT | `/properties/{property_id}` |  |
| DELETE | `/properties/{property_id}` |  |
| GET | `/properties/{property_id}/compare/{other_id}` |  |
| PUT | `/properties/{property_id}/coordinates` | Set (or correct) the coordinates of a property. |
| GET | `/properties/{property_id}/images` |  |
| GET | `/properties/{property_id}/investment` |  |
| GET | `/search` |  |

## property-intelligence

4 routes.

| Method(s) | Path | Purpose |
| --- | --- | --- |
| GET | `/property-intelligence/accounting-snapshot/{property_id}` | Per-property accounting snapshot: value, NOI, cap rate, ROI and active leases. |
| GET | `/property-intelligence/gis-score` | The Property-Intelligence GIS score for an address or property (0–100 + grade). |
| GET | `/property-intelligence/market-intelligence` | Regional market intelligence: pricing, factors, news momentum and forecast. |
| GET | `/property-intelligence/seller-intent/{contact_id}` | Score a CRM contact's likelihood of selling (0–100) with reasons and next action. |

## roles

16 routes.

| Method(s) | Path | Purpose |
| --- | --- | --- |
| GET | `/roles` | List portal roles. |
| POST | `/roles` | Create a custom role. |
| GET | `/roles/permissions` | The full permission catalogue. |
| GET | `/roles/summary` | Roles by portal area, permission count and per-role member counts. |
| GET | `/roles/{name}` | Fetch one role with its permissions and member count. |
| PUT | `/roles/{name}` | Update a role. |
| DELETE | `/roles/{name}` | Delete a custom role. |
| GET | `/roles/{name}/users` | All users holding a given role. |
| GET | `/users/{user_id}/permissions` | A user's effective roles and permissions. |
| POST | `/users/{user_id}/permissions` | Grant an extra permission directly to a user. |
| GET | `/users/{user_id}/permissions/check` | Check whether a user holds a permission. |
| DELETE | `/users/{user_id}/permissions/{permission}` | Revoke a directly-granted permission. |
| GET | `/users/{user_id}/roles` | A user's roles and primary role. |
| PUT | `/users/{user_id}/roles` | Replace a user's whole role set. |
| POST | `/users/{user_id}/roles` | Grant one role to a user. |
| DELETE | `/users/{user_id}/roles/{role}` | Remove one role from a user. |

## routing

8 routes.

| Method(s) | Path | Purpose |
| --- | --- | --- |
| GET | `/gis/road-classes` | Road classes with their per-mode speeds. |
| GET | `/gis/road-networks` | List the road networks available for routing. |
| POST | `/gis/road-networks` | Register a custom routable road network from polyline ``ways``. |
| GET | `/gis/route` | Best route (plus alternatives) between two points, on foot or by car. |
| GET | `/gis/route/compare` | Compare every travel mode between two points (comma-separated ``modes`` optional). |
| GET | `/gis/route/map` | HTML map of the best route and its alternatives. |
| POST | `/gis/route/matrix` | Distance/time matrix between POIs or coordinates. |
| GET | `/gis/travel-modes` | Available travel modes (on foot, bicycle, motor car) and their road speeds. |

## system

4 routes.

| Method(s) | Path | Purpose |
| --- | --- | --- |
| GET | `/` |  |
| GET | `/fastapi-info` |  |
| GET | `/health` |  |
| GET | `/info` |  |

## tools

70 routes.

| Method(s) | Path | Purpose |
| --- | --- | --- |
| GET | `/tools/area-units` | Area units and marla standards supported by the converters. |
| POST | `/tools/cad/compare-revisions` | Compare two revisions of a plan: counts, extents and added/removed items. |
| POST | `/tools/cad/dxf-preview` | Parse an ASCII DXF and render it to SVG (line/polyline/circle/text). |
| GET | `/tools/cad/formats` | Supported drawing formats and what each can actually preview/convert. |
| POST | `/tools/cad/inspect` | Detect a drawing's format from its name/first bytes and report capabilities. |
| POST | `/tools/cad/layout-sheet` | A printable plot-layout sheet (SVG) with a title block and scale bar. |
| GET | `/tools/calculators` | The calculators offered by the Tools Center, with their inputs and engines. |
| POST | `/tools/calculators/appreciation` | Property appreciation and investment-growth projection with scenario bands. |
| POST | `/tools/calculators/build-timeline` | Phase-weighted construction timeline (delegates to the construction wing). |
| POST | `/tools/calculators/capital-gains` | Capital-gains tax on a disposal, by holding period and filer status. |
| POST | `/tools/calculators/commission` | Agent commission on a sale, with optional output VAT. |
| POST | `/tools/calculators/construction-cost` | Construction-cost estimate (delegates to the construction wing's engine). |
| POST | `/tools/calculators/installment` | Developer-style installment plan: down payment, markup and monthly amount. |
| POST | `/tools/calculators/joint-investment` | Split a profit between partners pro-rata to capital, with each partner's ROI. |
| POST | `/tools/calculators/material-quantities` | Approximate material take-off (delegates to the construction wing). |
| POST | `/tools/calculators/mortgage` | Home-loan monthly installment, total interest and full amortisation schedule. |
| POST | `/tools/calculators/price-per-unit` | Price per sqft / sqyd / sqm / marla for a listing. |
| POST | `/tools/calculators/rent-vs-buy` | Compare buying against renting over a holding period. |
| POST | `/tools/calculators/rental-yield` | Gross and net rental yield with payback period and cap rate. |
| POST | `/tools/calculators/transfer-costs` | Stamp duty, CVT, registration, mutation and withholding on a transfer. |
| GET | `/tools/calendar/gregorian` | Convert a Hijri date to the predicted Gregorian date. |
| GET | `/tools/calendar/hijri` | Convert a Gregorian date (YYYY-MM-DD) to the predicted Hijri date. |
| GET | `/tools/calendar/holidays` | Pakistan public holidays for a year: fixed national days + predicted Islamic ones. |
| POST | `/tools/calendar/ics` | Render events as a downloadable iCalendar (.ics) feed. |
| POST | `/tools/calendar/milestones` | Date-stamp a construction timeline into a milestone calendar (+ .ics). |
| GET | `/tools/calendar/occasions` | The main Islamic occasions inside a Gregorian year (predicted). |
| POST | `/tools/calendar/possession` | A booking + installment + possession payment schedule with due dates (+ .ics). |
| POST | `/tools/calendar/reminders` | Turn dated property events into reminders (possession, installments, expiries). |
| GET | `/tools/catalog` | The tool cards, optionally filtered by category or launch phase. |
| GET | `/tools/catalog/{key}` | One tool card by key (e.g. ``mortgage``, ``georeference``, ``calendar``). |
| GET | `/tools/categories` | The Tools Center categories and their tool counts. |
| GET | `/tools/convert/area` | Convert between sqft / sqyd / sqm / marla / kanal / acre / hectare. |
| GET | `/tools/convert/area-table` | Show an area in every supported unit at once. |
| GET | `/tools/convert/length` | Convert between feet, inches, yards, metres, centimetres and kilometres. |
| POST | `/tools/documents/brochure` | Build a branded text brochure PDF from a list of sections. |
| GET | `/tools/documents/convert-guide` | Explain what a heavier conversion needs (and why), plus upload-safety notes. |
| POST | `/tools/documents/images-to-pdf` | Combine JPEG images into a PDF (native, no re-encoding). |
| POST | `/tools/documents/pdf-info` | Basic PDF inspection: page count and declared size. |
| GET | `/tools/documents/resize-plan` | Compute a contain-fit resize target without touching the pixels. |
| POST | `/tools/documents/text-to-pdf` | Create a simple text/listings PDF (dependency-free). |
| GET | `/tools/documents/tools` | The document/conversion tools and whether each is native or needs a dependency. |
| POST | `/tools/gis/aerial-compare` | Compare dated aerial/satellite scenes: order, resolution and change. |
| GET | `/tools/gis/crs` | Common coordinate reference systems with measurement guidance. |
| POST | `/tools/gis/export` | Export points/lines/polygons as GeoJSON or KML. |
| POST | `/tools/gis/georeference` | Fit an image-pixel → WGS84 transform from control points (affine/similarity). |
| POST | `/tools/gis/import` | Parse GeoJSON or KML text into [lat, lon] coordinate lists. |
| POST | `/tools/gis/measure` | Distance, perimeter, area, centroid and bbox for [lat, lon] points. |
| POST | `/tools/gis/nearby` | Locate POIs within a radius of an origin [lat, lon], nearest first. |
| POST | `/tools/gis/polygon-area` | Area of a polygon from its [lat, lon] coordinates, in the requested unit. |
| POST | `/tools/gis/transform` | Apply a georeference matrix (px→geo forward, or geo→px with to_geo=False). |
| GET | `/tools/overview` | Counts by category and phase for the Tools Center, plus configuration. |
| POST | `/tools/photo/geotag-batch` | Geotag several photos with the same coordinate. |
| GET | `/tools/photo/privacy-check` | Advise on sharing precise residential coordinates (opt-in, fuzzing). |
| POST | `/tools/photo/read-gps` | Read GPS coordinates, altitude and time from a JPEG's EXIF metadata. |
| POST | `/tools/photo/report` | A property photo report: markers, summary table and an embeddable map. |
| POST | `/tools/photo/write-gps` | Embed/replace GPS coordinates in a JPEG's EXIF (returns new base64 bytes). |
| GET | `/tools/plot/diagram` | A printable SVG diagram of a rectangular plot with dimensions and area. |
| GET | `/tools/plot/dimensions` | Length / width / perimeter / diagonal of a rectangular plot from its area. |
| GET | `/tools/plot/studio` | One-shot plot brief: conversion, dimensions, diagram and optional build cost. |
| GET | `/tools/portal` | The Tools & Utilities page (HTML): Tools Center, calculators, reference tables. |
| GET | `/tools/portal.html` | Alias of ``/tools/portal`` that always serves HTML. |
| GET | `/tools/projects` | List saved tool projects, optionally filtered by tool key. |
| POST | `/tools/projects` | Save a tool run as a reusable project (personalised tools). |
| GET | `/tools/projects/{project_id}` | One saved tool project by id. |
| DELETE | `/tools/projects/{project_id}` | Delete a saved tool project. |
| POST | `/tools/reports/comparison` | Side-by-side comparison of listings with derived price/sqft and yield. |
| POST | `/tools/reports/csv` | Serialise rows of dicts to CSV text. |
| POST | `/tools/reports/investment-summary` | Investment summary built on the accounting ROI engine (with scenarios). |
| POST | `/tools/reports/markdown` | Serialise rows of dicts to a Markdown table. |
| POST | `/tools/reports/plot-inventory` | Plot inventory: area in sqft / marla / kanal with price per unit. |

## transactions

16 routes.

| Method(s) | Path | Purpose |
| --- | --- | --- |
| POST | `/transactions` | Open a transaction with its milestone/deadline checklist. |
| GET | `/transactions` | List transactions. |
| GET | `/transactions/deadlines` | Every transaction milestone due within the horizon. |
| POST | `/transactions/offers/{offer_id}/respond` | Respond to an offer (counter / accept / reject / withdraw). |
| GET | `/transactions/stages` | The transaction lifecycle stages and configuration. |
| POST | `/transactions/terms/extract` | Extract key contract terms from agreement text. |
| GET | `/transactions/{tx_id}` | One transaction with milestones, terms and offers. |
| PUT | `/transactions/{tx_id}` | Update a transaction's stage, price, parties or commission rate. |
| POST | `/transactions/{tx_id}/close` | Close a transaction: commission, VAT, revenue share, ledger and payouts. |
| POST | `/transactions/{tx_id}/milestones` | Add a custom milestone/deadline. |
| POST | `/transactions/{tx_id}/milestones/{key}/complete` | Mark a milestone complete. |
| POST | `/transactions/{tx_id}/offers` | Record an offer on a transaction. |
| GET | `/transactions/{tx_id}/progress` | Completion %, overdue milestones and next deadline. |
| POST | `/transactions/{tx_id}/report` | Printable transaction/closing report (HTML). |
| GET | `/transactions/{tx_id}/signatures` | E-signature status for a transaction. |
| POST | `/transactions/{tx_id}/signatures` | Record an e-signature request / signing. |

## ui

3 routes.

| Method(s) | Path | Purpose |
| --- | --- | --- |
| GET | `/i18n/languages` | Languages available for maps, reports and the ticker (code, name, direction). |
| GET | `/i18n/strings/{lang}` | Localisation dictionary for one language (English source -> translation). |
| GET | `/ui/themes` | Available UI themes and the CSS custom properties each one sets. |

## units

1 routes.

| Method(s) | Path | Purpose |
| --- | --- | --- |
| GET | `/units/convert` |  |

