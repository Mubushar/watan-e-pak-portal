# MCP tool reference

Auto-generated from `server.py` — **605 tools** across **30 groups**. Regenerate with `uv run python docs/_gen/gen_docs.py` from the repository root's `backend/`.

Legend: `?` = optional parameter. Types are the JSON-Schema types the server advertises to MCP clients.

| Group | Tools |
| --- | --- |
| [tools](#tools) | 69 |
| [messaging](#messaging) | 66 |
| [pmo](#pmo) | 58 |
| [gis](#gis) | 51 |
| [authentication](#authentication) | 36 |
| [accounting](#accounting) | 32 |
| [crm](#crm) | 28 |
| [maintenance](#maintenance) | 27 |
| [hierarchy](#hierarchy) | 26 |
| [construction](#construction) | 23 |
| [general](#general) | 20 |
| [commercial](#commercial) | 16 |
| [transactions](#transactions) | 16 |
| [content](#content) | 15 |
| [agents](#agents) | 14 |
| [advertising](#advertising) | 13 |
| [poi](#poi) | 13 |
| [marketing](#marketing) | 12 |
| [aoi](#aoi) | 11 |
| [leasing](#leasing) | 11 |
| [intelligence](#intelligence) | 10 |
| [portal](#portal) | 9 |
| [finance](#finance) | 8 |
| [investment](#investment) | 5 |
| [news](#news) | 5 |
| [images](#images) | 4 |
| [memory](#memory) | 3 |
| [search](#search) | 2 |
| [market](#market) | 1 |
| [rag](#rag) | 1 |

## accounting

32 tools.

| Tool | Purpose | Parameters |
| --- | --- | --- |
| `accounting_account_balance` | Debit/credit movement and the signed balance of a single account. | `code`:string, `as_of`?:optional |
| `accounting_balance_sheet` | Assets, liabilities and equity at a point in time. | `as_of`?:optional |
| `accounting_budget_create` | Create a budget (``account_code -> amount``) for a fiscal year and scope. | `name`:string, `lines`:object, `fiscal_year`?:string="", `scope`?:string="portfolio", `scope_id`?:optional, `notes`?:optional |
| `accounting_budget_list` | List every budget. | — |
| `accounting_budget_variance` | Budget vs actual variance with favourable/unfavourable flags. | `budget_id`:string |
| `accounting_cash_flow` | Operating / investing / financing cash-flow statement. | `from_date`?:optional, `to_date`?:optional |
| `accounting_chart_of_accounts` | The chart of accounts with live balances (filter by type / subtype). | `account_type`?:optional, `subtype`?:optional, `active_only`?:boolean=false |
| `accounting_create_account` | Add a ledger account. ``code`` is the primary key; ``account_type`` is | `code`:string, `name`:string, `account_type`?:string="asset", `subtype`?:optional, `parent_code`?:optional, `normal_side`?:optional, `description`?:optional, `opening_balance`?:number=0.0 |
| `accounting_dashboard` | Finance dashboard: assets, cash, AR/AP, revenue, profit, overdue and ratios. | `as_of`?:optional |
| `accounting_expense_create` | Capture an expense (posted to the ledger automatically). | `amount`:number, `account_code`?:string="5900", `category`?:string="misc", `date`?:optional, `vendor`?:optional, `description`?:optional, `tax_amount`?:number=0.0, `paid`?:boolean=true, `property_id`?:optional, `scheme_id`?:optional, `city_id`?:optional |
| `accounting_general_ledger` | Chronological postings for one account with a running balance. | `account_code`:string, `from_date`?:optional, `to_date`?:optional |
| `accounting_generate_rent_invoices` | Raise this period's rent invoices for every due lease (idempotent per month). | `period_month`?:optional, `year`?:optional, `auto_post`?:boolean=true |
| `accounting_info` | Accounting configuration, allowed values and live record counts. | — |
| `accounting_invoice_aging` | Receivable/payable ageing buckets (current, 1-30, 31-60, 61-90, 90+). | `as_of`?:optional, `invoice_type`?:optional |
| `accounting_invoice_create` | Create a receivable (we bill) or payable (we are billed) invoice with tax. | `counterparty`:string, `lines`:array<object>, `invoice_type`?:string="receivable", `issue_date`?:optional, `due_date`?:optional, `tax_rate`?:optional, `property_id`?:optional, `scheme_id`?:optional, `city_id`?:optional, `lease_id`?:optional, `notes`?:optional, `auto_post`?:boolean=false |
| `accounting_invoice_get` | One invoice (by id or number) with its payments. | `invoice_id`:string |
| `accounting_invoice_list` | List invoices with balances and overdue flags. | `invoice_type`?:optional, `status`?:optional, `counterparty`?:optional, `property_id`?:optional, `overdue_only`?:boolean=false, `limit`?:integer=50 |
| `accounting_invoice_post` | Post an invoice to the ledger (AR/AP + income/expense + tax). | `invoice_id`:string |
| `accounting_journal_get` | Fetch one journal entry with its lines and totals. | `entry_id`:string |
| `accounting_journal_list` | Recent journal entries, filtered by date / source / account / property. | `from_date`?:optional, `to_date`?:optional, `source`?:optional, `account`?:optional, `property_id`?:optional, `limit`?:integer=50 |
| `accounting_journal_post` | Post a balanced double-entry journal entry. | `lines`:array<object>, `date`?:optional, `memo`?:optional, `reference`?:optional, `created_by`?:optional |
| `accounting_journal_void` | Void a journal entry (kept in the audit trail, removed from the statements). | `entry_id`:string, `reason`?:optional |
| `accounting_lease_create` | Create a lease — it drives the rent roll and automatic rent invoices. | `tenant`:string, `rent_amount`:number, `property_id`?:optional, `unit_label`?:optional, `start_date`?:optional, `end_date`?:optional, `billing_cycle`?:string="monthly", `escalation_rate`?:optional, `security_deposit`?:number=0.0, `tenant_id`?:optional, `city_id`?:optional, `scheme_id`?:optional, `notes`?:optional |
| `accounting_lease_list` | List leases with their monthly and annual rent. | `status`?:optional, `property_id`?:optional, `scheme_id`?:optional, `city_id`?:optional |
| `accounting_payment_record` | Record a receipt (``in``) or disbursement (``out``) and allocate it to an invoice. | `amount`:number, `invoice_id`?:optional, `direction`?:string="in", `method`?:string="bank_transfer", `account_code`?:string="1010", `date`?:optional, `counterparty`?:optional, `reference`?:optional, `notes`?:optional |
| `accounting_profit_and_loss` | Profit & loss for a period, optionally scoped to a property / scheme / city. | `from_date`?:optional, `to_date`?:optional, `property_id`?:optional, `scheme_id`?:optional, `city_id`?:optional |
| `accounting_property_performance` | Property-level P&L plus its rent roll, yields and net operating income. | `property_id`:string, `from_date`?:optional, `to_date`?:optional |
| `accounting_ratios` | Liquidity, leverage and profitability ratios (current, quick, D/E, ROE, ROA, margin). | `as_of`?:optional |
| `accounting_rent_roll` | Active leases, contracted rent and deposits held. | `as_of`?:optional |
| `accounting_trial_balance` | Trial balance — debit/credit column per account, with a balanced check. | `as_of`?:optional |
| `accounting_update_account` | Rename / reclassify / deactivate a ledger account. | `code`:string, `name`?:optional, `subtype`?:optional, `description`?:optional, `active`?:optional |
| `get_accounting_snapshot` | Accounting snapshot for one property: value, income, NOI, cap rate and leverage ROI. | `property_id`:string, `rental_yield`?:number=0.045, `operating_expense_rate`?:number=0.3 |

## advertising

13 tools.

| Tool | Purpose | Parameters |
| --- | --- | --- |
| `ad_active` | The live, in-window, on-target creatives for a slot — priority- and | `slot`?:optional, `category`?:optional, `city`?:optional, `scheme`?:optional, `lang`?:optional, `limit`?:optional |
| `ad_categories` | Advertisement categories (smart technology, construction techniques, materials …). | — |
| `ad_create` | Create an advertisement creative (a sponsored card placed in a slot). | `title`:string, `headline`:string, `advertiser`?:string="", `category`?:string="services", `slot`?:string="infeed", `body`?:optional, `keywords`?:optional, `cta_label`?:optional, `cta_url`?:optional, `media_url`?:optional, `image_url`?:optional, `tags`?:optional, `contact`?:optional, `phone`?:optional, `price_text`?:optional, `offer`?:optional, `city`?:optional, `scheme`?:optional, `lang`?:optional, `priority`?:integer=100, `weight`?:number=1.0, `status`?:string="active", `valid_from`?:optional, `valid_until`?:optional, `budget`?:number=0.0, `pricing`?:string="flat", `rate`?:number=0.0 |
| `ad_delete` | Delete an advertisement creative. | `ad_id`:string |
| `ad_get` | Fetch one advertisement by id. | `ad_id`:string |
| `ad_list` | List advertisement creatives with their live status and performance counters. | `category`?:optional, `slot`?:optional, `status`?:optional, `advertiser`?:optional, `tag`?:optional, `limit`?:integer=100 |
| `ad_performance` | Impression / click / CTR / budget performance — one ad, or the whole book. | `ad_id`?:optional |
| `ad_preview` | Render one advertisement section as standalone, themed HTML. | `slot`?:string="infeed", `category`?:optional, `lang`?:string="en", `theme`?:string="auto", `city`?:optional, `scheme`?:optional, `limit`?:optional |
| `ad_report` | Render a printable **advertising report**: every slot's live creatives plus | `lang`?:string="en", `theme`?:string="auto" |
| `ad_section` | Build one advertisement *section* (heading + resolved creatives) as data. | `slot`?:string="infeed", `category`?:optional, `city`?:optional, `scheme`?:optional, `lang`?:optional, `limit`?:optional, `heading`?:optional |
| `ad_slots` | Advertisement slots (hero, banner, sidebar, in-feed, footer, newsletter). | — |
| `ad_track` | Record ``impression`` / ``click`` / ``spend`` events for an advertisement. | `ad_id`:string, `event`?:string="impression", `count`?:integer=1 |
| `ad_update` | Update an advertisement creative (including pausing/resuming it). | `ad_id`:string, `title`?:optional, `headline`?:optional, `body`?:optional, `advertiser`?:optional, `category`?:optional, `slot`?:optional, `cta_label`?:optional, `cta_url`?:optional, `image_url`?:optional, `contact`?:optional, `phone`?:optional, `price_text`?:optional, `offer`?:optional, `tags`?:optional, `lang`?:optional, `priority`?:optional, `weight`?:optional, `status`?:optional, `valid_from`?:optional, `valid_until`?:optional, `budget`?:optional, `pricing`?:optional, `rate`?:optional |

## agents

14 tools.

| Tool | Purpose | Parameters |
| --- | --- | --- |
| `agent_approve` | Approve a paused agent run (human-in-the-loop gate) and optionally finish executing it. | `run_id`:string, `approver`?:string="user", `execute`?:boolean=true |
| `agent_get` | One agent's full definition by key (e.g. ``conversational_buyer_agent``). | `key`:string |
| `agent_move_likelihood` | Score a CRM lead's likelihood of moving (0–100) from lifecycle and engagement signals. | `lead_id`:string |
| `agent_orchestrate` | Plan a multi-agent hand-off chain for a shared objective (comma-separated agent keys). | `objective`:string, `agents_csv`:string |
| `agent_plan` | Plan (but do not execute) an agent run: the explicit ``intake → tools → review → deliver`` steps. | `agent_key`:string, `objective`?:string="", `subject_type`?:optional, `subject_id`?:optional |
| `agent_products` | The eight roadmap products, their priority (P0–P2) and their agent modules. | `priority`?:optional |
| `agent_run` | Execute an agent run against the live portal. | `agent_key`:string, `objective`?:string="", `text`?:optional, `subject_type`?:optional, `subject_id`?:optional, `approve`?:boolean=true, `extra`?:optional |
| `agent_run_get` | One agent run with its steps, outputs, approvals and metrics. | `run_id`:string |
| `agent_runs` | Recorded agent runs (the audit trail), optionally filtered by agent or status. | `agent_key`?:optional, `status`?:optional |
| `agent_seller_intent` | Score how likely a contact is to sell (0–100) and recommend the next action. | `equity_pct`?:number=0.0, `holding_years`?:number=0.0, `market_heat`?:number=0.5, `life_event`?:optional, `fsbo_signal`?:boolean=false, `engagement_score`?:integer=40 |
| `agent_smart_actions` | The prioritised "Smart Actions" morning brief across deals, tasks, transactions, | `limit`?:integer=15 |
| `agentic_portal` | Render the **Agentic OS** portal page (HTML): the product roadmap, the agent | `lang`?:string="en", `theme`?:string="auto" |
| `agents_catalog` | The agent catalogue: 8 roadmap product agents plus specialist sub-agents. | `category`?:optional, `product`?:optional, `priority`?:optional, `autonomy`?:optional |
| `agents_overview` | Counts, products, autonomy mix and run activity across the Agentic OS. | — |

## aoi

11 tools.

| Tool | Purpose | Parameters |
| --- | --- | --- |
| `aoi_analyze` | Full analytics for an area of interest: area & valuation, population, cost & economic | `aoi_id`:string, `years`?:integer=5 |
| `aoi_compare` | Compare two or more areas of interest side by side. | `aoi_ids`:array<string> |
| `aoi_create` | Save an area of interest: ``circle`` (centre + radius), ``polygon`` ([[lat, lon], ...]), | `name`:string, `kind`?:string="circle", `description`?:optional, `center_latitude`?:optional, `center_longitude`?:optional, `radius_m`?:optional, `coordinates`?:optional, `bounds`?:optional, `entity_type`?:optional, `entity_id`?:optional, `city`?:optional, `scheme`?:optional, `tags`?:optional, `watch_categories`?:optional, `watch_alert_threshold`?:number=0.0, `created_by`?:optional, `notes`?:optional |
| `aoi_delete` | Delete an area of interest. | `aoi_id`:string |
| `aoi_get` | Fetch one area of interest (by id or name) with its resolved geometry. | `aoi_id`:string |
| `aoi_list` | List saved areas of interest. | `kind`?:optional, `city`?:optional, `scheme`?:optional |
| `aoi_map` | Self-contained HTML map of an area of interest with its boundary, properties and POIs. | `aoi_id`:string, `base_map`?:optional, `include_properties`?:boolean=true, `include_pois`?:boolean=true, `lang`?:string="en", `theme`?:string="auto" |
| `aoi_report` | Printable HTML report for an area of interest (analysis + POI + outlook + ticker). | `aoi_id`:string, `years`?:integer=5, `include_map`?:boolean=true, `include_news`?:boolean=true, `lang`?:string="en", `theme`?:string="auto" |
| `aoi_stats` | Quick statistics for an area of interest: area, properties, value, population, POIs. | `aoi_id`:string |
| `aoi_update` | Rename, re-tag or re-configure the news watch of an area of interest. | `aoi_id`:string, `name`?:optional, `description`?:optional, `tags`?:optional, `watch_categories`?:optional, `watch_alert_threshold`?:optional, `notes`?:optional |
| `aoi_watch` | News watch: relevant headlines for an area plus alerts when the impact of a | `aoi_id`:string, `days`?:integer=120 |

## authentication

36 tools.

| Tool | Purpose | Parameters |
| --- | --- | --- |
| `auth_assign_role` | Grant one role to a portal user. | `user_id`:string, `role`:string |
| `auth_check_permission` | Check whether a user holds a permission (via roles or a direct grant). | `user_id`:string, `permission`:string |
| `auth_config` | OTP/session/password policy plus live counters. | — |
| `auth_create_role` | Create a custom portal role from a set of permissions. | `name`:string, `label`:string, `description`?:optional, `portal_area`?:string="staff", `level`?:integer=20, `permissions`?:optional |
| `auth_delete_role` | Delete a custom role (system or in-use roles are protected). | `name`:string |
| `auth_events` | Authentication audit trail (signup, login, OTP sent/failed/verified, …). | `limit`?:integer=50 |
| `auth_get_otp` | Dev helper: return the newest unconsumed OTP for an identifier. | `identifier`:string, `purpose`?:string="signup" |
| `auth_get_role` | Fetch one role with its full permission list and member count. | `name`:string |
| `auth_grant_permission` | Grant one extra permission directly to a user, on top of their roles. | `user_id`:string, `permission`:string |
| `auth_list_otps` | List outstanding verification codes (plaintext only while ``PORTAL_AUTH_EXPOSE_OTP`` is on). | `identifier`?:optional, `purpose`?:optional, `limit`?:integer=25 |
| `auth_list_roles` | List portal roles (public / client / staff / admin) with their permissions. | `portal_area`?:optional |
| `auth_list_users` | List accounts, optionally filtered by role and/or status. | `role`?:optional, `status`?:optional |
| `auth_login` | Password login for a verified account. Returns a bearer token. | `identifier`:string, `password`:string |
| `auth_logout` | Revoke the bearer token. | `token`:string |
| `auth_me` | Return the account behind a bearer token. | `token`:string |
| `auth_notifications` | The simulated SMS/e-mail outbox — every OTP that was 'sent'. | `channel`?:optional, `limit`?:integer=25 |
| `auth_permissions` | The full permission catalogue (resource.action) with descriptions. | — |
| `auth_refresh` | Exchange a valid token for a fresh one (the old one is revoked). | `token`:string |
| `auth_request_otp` | Start a passwordless login by sending an OTP to the email/mobile. | `identifier`:string |
| `auth_request_password_reset` | Send a password-reset code to the account's email/mobile. | `identifier`:string |
| `auth_resend_otp` | Re-send a verification code (subject to a cooldown and an hourly cap). | `identifier`:string, `purpose`?:string="signup" |
| `auth_reset_password` | Reset a password with the reset code (revokes all existing sessions). | `identifier`:string, `code`:string, `new_password`:string |
| `auth_revoke_permission` | Withdraw a directly-granted permission from a user. | `user_id`:string, `permission`:string |
| `auth_revoke_role` | Remove one role from a portal user (a user always keeps at least one). | `user_id`:string, `role`:string |
| `auth_role_summary` | Roles by portal area, the permission catalogue size and per-role member counts. | — |
| `auth_set_password` | Set or change the password of the signed-in user. | `token`:string, `new_password`:string, `current_password`?:optional |
| `auth_set_role` | Change an account's role (user / agent / admin). | `user_id`:string, `role`:string |
| `auth_set_status` | Activate / suspend an account (suspending revokes its sessions). | `user_id`:string, `status`:string |
| `auth_set_user_roles` | Replace a user's full role set (the highest-level role becomes primary). | `user_id`:string, `roles`:array<string> |
| `auth_signup` | Create an account with an email and/or a mobile number. | `email`?:optional, `mobile`?:optional, `password`?:optional, `name`?:optional, `role`?:string="user" |
| `auth_update_role` | Update a role (system roles keep their permissions but may be re-labelled). | `name`:string, `label`?:optional, `description`?:optional, `portal_area`?:optional, `level`?:optional, `permissions`?:optional |
| `auth_user_permissions` | The effective roles and permissions for a user (by id or email/mobile). | `user_id`?:optional, `identifier`?:optional |
| `auth_user_roles` | The roles held by a user, their primary role and their effective permissions. | `user_id`?:optional, `identifier`?:optional |
| `auth_users_by_role` | All portal users holding a given role. | `role`:string |
| `auth_verify_login_otp` | Complete a passwordless login with the OTP; returns a bearer token. | `identifier`:string, `code`:string |
| `auth_verify_otp` | Verify the signup/login/reset OTP. Activating a signup returns a bearer token. | `identifier`:string, `code`:string, `purpose`?:string="signup" |

## commercial

16 tools.

| Tool | Purpose | Parameters |
| --- | --- | --- |
| `commercial_bill` | Build a usage-based billing statement (plan fee + overage + VAT) for an account. | `account`:string, `plan_key`?:optional, `days`?:integer=30 |
| `commercial_gtm` | The go-to-market playbook: product prioritisation (P0–P2) and the four principles. | — |
| `commercial_meter_usage` | Record a metered usage event (a billable MCP tool call) for an account. | `account`:string, `tool`:string, `units`?:integer=1, `product`?:optional, `unit_price`?:optional |
| `commercial_payouts` | Recorded payouts, optionally filtered by payee or status. | `account`?:optional, `status`?:optional |
| `commercial_plan` | One pricing plan by key (e.g. ``mcp_growth``). | `key`:string |
| `commercial_plans` | Subscription / usage plans (price, interval, included units, overage rate, seats). | `product`?:optional |
| `commercial_portal` | Render the **Commercialization wing** portal page (HTML): product catalogue, pricing | `lang`?:string="en", `theme`?:string="auto" |
| `commercial_pricing_matrix` | The hybrid-pricing matrix (subscription + usage + performance + licence) with the GTM playbook. | — |
| `commercial_product` | One commercial product by key (e.g. ``broker_ai_workspace``). | `key`:string |
| `commercial_products` | The commercial product catalogue: the 8 products with segment, pricing models, | `category`?:optional, `priority`?:optional |
| `commercial_recommend_package` | Recommend the best-fit plan for a segment/seat-count/usage and estimate the monthly bill. | `segment`:string, `seats`?:integer=1, `expected_calls`?:integer=0, `product`?:optional |
| `commercial_record_payout` | Record a payee payout (agent / platform / agency) against a transaction commission. | `transaction_id`:string, `gross_commission`:number, `payee`:string, `share_pct`:number, `role`?:string="agent" |
| `commercial_revenue_share` | Performance revenue share: split a commission into platform and partner shares. | `commission_gross`:number, `platform_share`?:number=0.2 |
| `commercial_subscribe` | Create a subscription for an account on a plan. | `account`:string, `plan_key`:string, `seats`?:integer=1 |
| `commercial_subscriptions` | Active subscriptions (optionally for one account). | `account`?:optional |
| `commercial_usage` | Usage summary for an account over a window, broken down by tool. | `account`:string, `days`?:integer=30 |

## construction

23 tools.

| Tool | Purpose | Parameters |
| --- | --- | --- |
| `construction_advisory` | Recommend the best technique, foundation and guidelines for a site given its soil, | `plot_area`:number, `floors`?:integer=2, `building_type`?:string="house", `city`?:optional, `soil`?:string="sandy_loam", `seismic_zone`?:string="2A", `budget_per_sqft`?:optional |
| `construction_approvals` | The NOC / approval workflow for a project type: steps, authority, documents and | `project_type`?:string="house", `city`?:optional |
| `construction_compare` | Compare competing construction techniques by cost, unit rate and build speed. | `covered_area`:number, `floors`?:integer=1, `building_type`?:string="house", `quality_tier`?:string="standard", `city`?:optional, `category`?:string="structure" |
| `construction_element_rates` | BOQ element unit rates (material / labour / plant / overhead) used for rate analysis. | — |
| `construction_estimate` | Parameterised construction-cost estimate: element-wise build-up, preliminaries, | `covered_area`:number, `floors`?:integer=1, `building_type`?:string="house", `quality_tier`?:string="standard", `system`?:string="rcc_frame", `city`?:optional, `plot_area`?:optional, `escalation_years`?:number=0.0 |
| `construction_estimate_get` | One saved construction estimate by id. | `estimate_id`:string |
| `construction_estimate_save` | Compute a construction estimate and persist it for the project book. | `title`:string, `covered_area`:number, `floors`?:integer=1, `building_type`?:string="house", `quality_tier`?:string="standard", `system`?:string="rcc_frame", `city`?:optional, `plot_area`?:optional, `escalation_years`?:number=0.0, `notes`?:optional |
| `construction_estimates` | Saved construction estimates in the project book. | `building_type`?:optional, `city`?:optional |
| `construction_guidelines` | Building codes, byelaws and guidelines (zoning/setbacks, FAR/height, structural, | `category`?:optional, `authority`?:optional, `building_type`?:optional |
| `construction_hse` | Health, safety & environment (HSE) rules for construction sites. | — |
| `construction_impact` | How upgrading construction quality moves market value, rent, yield and payback — | `covered_area`:number, `building_type`?:string="house", `city`?:optional, `from_tier`?:string="standard", `to_tier`?:string="premium", `market_rate_sqft`?:number=12000.0, `gross_yield`?:number=0.05, `floors`?:integer=1 |
| `construction_material` | One building material by key (e.g. ``cement_opc``, ``steel_60``). | `key`:string |
| `construction_materials` | Building-material catalogue with live unit rates, wastage, lead times, | `category`?:optional |
| `construction_overview` | Counts, category breakdowns and configuration for the construction wing. | — |
| `construction_portal` | Render the **Construction wing** portal page (HTML) — techniques, rates, codes, | `lang`?:string="en", `theme`?:string="auto" |
| `construction_qa` | Quality-assurance inspection checklists by construction stage. | `stage`?:optional |
| `construction_rate_analysis` | Rate analysis for one BOQ element: material, labour, plant and overhead build-up. | `element`:string, `city`?:optional |
| `construction_report` | Render a printable **construction cost report** (HTML) for one building: element | `covered_area`:number, `floors`?:integer=1, `building_type`?:string="house", `quality_tier`?:string="standard", `system`?:string="rcc_frame", `city`?:optional, `lang`?:string="en", `theme`?:string="auto" |
| `construction_takeoff` | Indicative material take-off (cement, steel, sand, aggregate, bricks, tiles, paint …) | `covered_area`:number, `quality_tier`?:string="standard", `building_type`?:string="house" |
| `construction_technique` | One construction technique / system by key (e.g. ``rcc_frame``, ``peb``). | `key`:string |
| `construction_techniques` | Catalogue of construction techniques / systems (RCC frame, steel, PEB, precast, | `category`?:optional, `building_type`?:optional, `max_floors`?:optional, `min_floors`?:optional |
| `construction_timeline` | Phase-weighted construction timeline (mobilisation → structure → finishes → handover). | `covered_area`:number, `floors`?:integer=1, `building_type`?:string="house", `system`?:string="rcc_frame" |
| `construction_trades` | Construction trades with current daily wage rates. | — |

## content

15 tools.

| Tool | Purpose | Parameters |
| --- | --- | --- |
| `content_contact` | The portal's contact directory: phone, e-mail, WhatsApp, offices, hours, social. | `channel_type`?:optional, `city`?:optional, `scheme`?:optional, `primary_only`?:boolean=false |
| `content_contact_add` | Add a contact channel (phone / email / whatsapp / office / hours / social / …). | `channel_type`:string, `label`:string, `value`:string, `url`?:optional, `hours`?:optional, `city`?:optional, `scheme`?:optional, `region`?:optional, `priority`?:integer=100, `is_primary`?:boolean=false, `notes`?:optional |
| `content_history` | The portal's company-history timeline, newest-facing, filterable by era and kind. | `kind`?:optional, `since`?:optional, `until`?:optional, `featured`?:optional |
| `content_history_add` | Add an entry to the company-history timeline. | `year`:integer, `title`:string, `description`:string, `kind`?:string="milestone", `month`?:optional, `tags`?:optional, `featured`?:boolean=false |
| `content_navigation` | The portal's navigation menu, derived from published nav-visible pages. | — |
| `content_overview` | Counts and breakdowns for every content page, timeline entry, contact, story and ad. | — |
| `content_page_create` | Create a portal content page. ``highlights`` are ``{label,value,sub}`` cards, | `key`:string, `title`:string, `category`?:string="about", `subtitle`?:optional, `summary`?:optional, `body`?:optional, `highlights`?:optional, `bullets`?:optional, `faqs`?:optional, `tags`?:optional, `nav_label`?:optional, `show_in_nav`?:boolean=true, `order`?:integer=100, `status`?:string="published" |
| `content_page_delete` | Delete a portal content page. | `key`:string |
| `content_page_get` | Fetch one content page by key (slug) or id. | `key`:string |
| `content_page_list` | List portal content pages (about, services, faq, policy …). | `category`?:optional, `tag`?:optional, `status`?:string="published", `nav_only`?:boolean=false |
| `content_page_update` | Update a portal content page. | `key`:string, `title`?:optional, `category`?:optional, `subtitle`?:optional, `summary`?:optional, `body`?:optional, `highlights`?:optional, `bullets`?:optional, `faqs`?:optional, `tags`?:optional, `nav_label`?:optional, `show_in_nav`?:optional, `order`?:optional, `status`?:optional |
| `content_portal_home` | Render the full public **portal home page** (HTML) — about, history, success | `lang`?:string="en", `theme`?:string="auto", `city`?:optional, `scheme`?:optional, `include_ticker`?:boolean=true, `include_stats`?:boolean=true |
| `content_site` | The complete portal site payload: nav, layout blocks, pages, history, contacts, | `lang`?:string="en", `city`?:optional, `scheme`?:optional |
| `content_success_stories` | Client success stories, case studies and testimonials. | `story_type`?:optional, `city`?:optional, `scheme`?:optional, `featured`?:optional, `tag`?:optional |
| `content_success_story_add` | Publish a success story (case study / testimonial / investment / milestone). | `title`:string, `story_type`?:string="case_study", `client_name`?:optional, `client_role`?:optional, `quote`?:optional, `rating`?:optional, `location`?:optional, `city`?:optional, `scheme`?:optional, `property_id`?:optional, `project_id`?:optional, `narrative`?:optional, `metrics`?:optional, `highlights`?:optional, `tags`?:optional, `featured`?:boolean=false, `date`?:optional |

## crm

28 tools.

| Tool | Purpose | Parameters |
| --- | --- | --- |
| `crm_add_agent` | Create a sales agent. | `name`:string, `email`?:optional, `phone`?:optional, `region`?:optional, `specialization`?:optional, `commission_rate`?:number=0.02 |
| `crm_add_customer` | Create a customer/contact directly. | `name`:string, `email`?:optional, `phone`?:optional, `type`?:string="buyer", `city_id`?:optional, `assigned_agent_id`?:optional, `notes`?:optional |
| `crm_add_lead` | Create a sales lead with an optional property interest. | `name`:string, `email`?:optional, `phone`?:optional, `source`?:string="website", `interest_use_type`?:optional, `interest_category`?:optional, `budget_min`?:optional, `budget_max`?:optional, `city_id`?:optional, `scheme_id`?:optional, `assigned_agent_id`?:optional, `notes`?:optional |
| `crm_add_task` | Create a CRM task/follow-up. | `title`:string, `description`?:optional, `assigned_agent_id`?:optional, `related_type`?:optional, `related_id`?:optional, `due_date`?:optional, `priority`?:string="medium" |
| `crm_assign_lead` | Assign a lead to an agent. | `lead_id`:string, `agent_id`:string |
| `crm_complete_task` | Mark a task as done/in_progress/cancelled. | `task_id`:string, `status`?:string="done" |
| `crm_convert_lead` | Convert a won lead into a customer. | `lead_id`:string, `customer_type`?:string="buyer" |
| `crm_create_deal` | Create a deal in the sales pipeline. | `title`:string, `amount`:number, `lead_id`?:optional, `customer_id`?:optional, `property_id`?:optional, `agent_id`?:optional, `stage`?:string="prospecting", `probability`?:integer=20, `expected_close_date`?:optional |
| `crm_dashboard` | High-level CRM dashboard: leads, deals, tasks and appointments at a glance. | — |
| `crm_get_agent` | Get a single agent plus their pipeline totals. | `agent_id`:string |
| `crm_get_customer` | Get a customer plus their deals and interactions. | `customer_id`:string |
| `crm_get_lead` | Get a lead with matched properties, interactions and deals. | `lead_id`:string |
| `crm_list_agents` | List sales agents. | `active_only`?:boolean=false |
| `crm_list_appointments` | List appointments, optionally filtered by status. | `status`?:optional |
| `crm_list_customers` | List customers, optionally filtered by type. | `type`?:optional |
| `crm_list_deals` | List deals with optional filters. | `stage`?:optional, `agent_id`?:optional |
| `crm_list_interactions` | List interactions for a given entity. | `entity_id`:string |
| `crm_list_leads` | List leads with optional filters. | `status`?:optional, `agent_id`?:optional, `city`?:optional, `min_score`?:optional |
| `crm_list_tasks` | List tasks with optional filters. | `status`?:optional, `agent_id`?:optional |
| `crm_log_interaction` | Log an interaction against a lead/customer/deal. | `entity_type`:string, `entity_id`:string, `summary`:string, `channel`?:string="call", `direction`?:string="outbound", `agent_id`?:optional |
| `crm_pipeline_summary` | Aggregate the deal pipeline by stage (count, value, weighted value). | — |
| `crm_schedule_appointment` | Schedule a site visit / appointment. | `title`:string, `scheduled_at`:string, `lead_id`?:optional, `customer_id`?:optional, `property_id`?:optional, `agent_id`?:optional, `notes`?:optional |
| `crm_update_agent` | Update a sales agent. | `agent_id`:string, `name`?:optional, `email`?:optional, `phone`?:optional, `region`?:optional, `specialization`?:optional, `active`?:optional, `rating`?:optional, `commission_rate`?:optional |
| `crm_update_deal_stage` | Move a deal to a new pipeline stage. | `deal_id`:string, `stage`:string, `probability`?:optional |
| `crm_update_lead` | Update a lead. | `lead_id`:string, `status`?:optional, `score`?:optional, `assigned_agent_id`?:optional, `budget_min`?:optional, `budget_max`?:optional, `notes`?:optional |
| `get_commission_projection` | Project commission from the live deal pipeline and the near-term closing schedule. | `agent_id`?:optional, `horizon_days`?:integer=90, `commission_rate`?:number=0.02 |
| `score_seller_intent` | Score how likely a CRM contact is to **sell** (0–100), with reasons and next action. | `contact_id`:string, `equity_pct`?:optional, `holding_years`?:optional, `market_heat`?:number=0.6, `life_event`?:optional, `fsbo_signal`?:boolean=false |
| `search_contacts` | Search CRM contacts with **live move-likelihood intent scoring**. | `query`?:optional, `status`?:optional, `min_intent_score`?:optional, `lifecycle`?:optional, `limit`?:integer=25 |

## finance

8 tools.

| Tool | Purpose | Parameters |
| --- | --- | --- |
| `finance_cap_rate` | Capitalisation rate and value multiple from net operating income and value. | `noi`:number, `value`:number |
| `finance_cash_on_cash` | Cash-on-cash return (annual pre-tax cash flow ÷ cash invested). | `annual_cash_flow`:number, `cash_invested`:number |
| `finance_investment_metrics` | NPV, IRR, payback, discounted payback, profitability index, equity multiple and ROI | `cashflows`:array<number>, `discount_rate`?:optional |
| `finance_mortgage_calculator` | Amortising mortgage: periodic payment, total interest and the full schedule. | `principal`:number, `annual_rate`?:optional, `years`?:optional, `payments_per_year`?:integer=12 |
| `finance_portfolio_roi` | Portfolio ROI: aggregates the listed properties, the rent roll and the accounting | `discount_rate`?:optional, `hold_years`?:integer=5, `appreciation_rate`?:number=0.075, `city`?:optional, `scheme`?:optional |
| `finance_property_roi` | Property ROI: gross/net rental yield, appreciation, leverage, IRR and exit proceeds. | `purchase_price`:number, `annual_rent`?:number=0.0, `annual_expenses`?:number=0.0, `hold_years`?:optional, `appreciation_rate`?:number=0.075, `discount_rate`?:optional, `down_payment_share`?:number=1.0, `loan_rate`?:optional, `loan_years`?:optional, `selling_cost_rate`?:number=0.02 |
| `finance_rental_yield` | Gross/net rental yield and cap rate for a property (uses its lease rent when omitted). | `property_id`:string, `annual_rent`?:optional, `annual_expenses`?:number=0.0 |
| `finance_roi_analysis` | Leveraged ROI analysis with pessimistic / base / optimistic scenarios. | `initial_investment`:number, `annual_cash_flow`?:number=0.0, `hold_years`?:optional, `terminal_value`?:number=0.0, `discount_rate`?:optional, `annual_growth`?:number=0.0, `annual_cost_inflation`?:number=0.0, `loan_amount`?:number=0.0, `loan_rate`?:optional, `loan_years`?:optional |

## general

20 tools.

| Tool | Purpose | Parameters |
| --- | --- | --- |
| `area_profile` | Population (estimate), size, density, development level, facilities, portal listings | `area`:string |
| `calculate_distance` | Haversine distance between two coordinates, in km and miles. | `lat1`:number, `lon1`:number, `lat2`:number, `lon2`:number |
| `convert_area` | Convert an area between sqft, sqm, sqyd, marla, kanal and acre. | `value`:number, `from_unit`:string, `to_unit`:string |
| `fastapi_info` | Describe the FastAPI integration layer and its REST endpoints. | — |
| `geo_locate` | Where a named place or area is (centre point and the matched areas). | `query`:string |
| `global_search` | Federated search across the whole portal: hierarchy, projects, POIs, AOIs, news, CRM and tools. | `query`:string, `limit`?:integer=10 |
| `health_check` | Liveness probe. | — |
| `map_view` | A map of a listing (or a named place / area) with the nearest schools, mosques, parks, | `listing_id`?:optional, `place`?:optional, `kinds`?:optional, `radius_km`?:number=2.0, `per_kind`?:integer=3 |
| `market_insights` | Aggregate market statistics for a city. | `city`:string |
| `market_trends` | Market trends for a market: pricing, factor index, news momentum, forecast and yields. | `city`?:optional, `scheme`?:optional, `years`?:integer=5, `days`?:integer=180 |
| `masterplan_at` | What the master plan shows around a listing, a place or a point (roads, plot sizes, parks, mosques …). | `place`?:optional, `listing_id`?:optional, `plan`?:optional, `latitude`?:optional, `longitude`?:optional, `radius_m`?:number=200.0 |
| `masterplan_list` | The DHA master plans loaded into the portal (outline, accuracy, map overlay, label counts). | — |
| `masterplan_search` | Find text on the master plans ("C10 commercial", "Jinnah Blvd", "masjid", "plot 23 street 13"). | `query`:string, `plan`?:optional, `category`?:optional, `limit`?:integer=20 |
| `masterplan_summary` | A DHA phase from its master plan: plot sizes, sectors / blocks, named roads, mosques, parks, | `plan`:string |
| `masterplan_view` | A section of a master plan to show: a readable close-up image (snapshot_url) and a map with | `plan`?:optional, `place`?:optional, `listing_id`?:optional, `radius_m`?:number=250.0 |
| `places_find` | Find and count real places (schools, malls, hospitals, mosques, universities, parks …) | `kind`?:optional, `area`?:optional, `near`?:optional, `radius_km`?:number=2.0, `name`?:optional, `limit`?:integer=15 |
| `property_availability` | Availability breakdown of the listing book (by status / use / category) with the listings. | `city`?:optional, `scheme`?:optional, `use_type`?:optional, `category`?:optional, `status`?:optional, `limit`?:integer=50 |
| `property_nearby` | Nearby places for a listing: the closest school, mosque, hospital, mall, park, | `property_id`:string, `radius_km`?:number=3.0 |
| `server_info` | Server metadata: version, capability counts and the data model. | — |
| `set_property_coordinates` | Set/update the GPS coordinates of a property. | `property_id`:string, `latitude`:number, `longitude`:number |

## gis

51 tools.

| Tool | Purpose | Parameters |
| --- | --- | --- |
| `analyze_property_gis` | GIS-enhanced property analysis: amenity, school, safety and commute scores. | `property_id`?:optional, `address`?:optional, `commute_destination`?:optional |
| `get_gis_score` | The *Property Intelligence* "GIS score" for an address or property (0–100 + grade). | `property_id`?:optional, `address`?:optional, `destination`?:optional |
| `gis_add_boundary` | Add a boundary polygon layer. ``coordinates`` are [lat, lon] pairs (min 3). | `entity_type`:string, `entity_id`:string, `name`:string, `coordinates`:array<array>, `style`?:optional |
| `gis_add_buffer_layer` | Add a buffer analysis layer: buffer an existing layer, a point, or a polygon. | `entity_type`:string, `entity_id`:string, `name`:string, `distance_m`:number, `source_layer_id`?:optional, `latitude`?:optional, `longitude`?:optional, `coordinates`?:optional, `style`?:optional, `layer_type`?:string="buffer" |
| `gis_add_layer` | Add a GeoJSON layer (master plan / boundary / zone / plot layout / road) to an entity. | `entity_type`:string, `entity_id`:string, `name`:string, `geojson`:object, `layer_type`?:string="master_plan", `description`?:optional, `base_map`?:optional, `style`?:optional, `z_index`?:integer=0, `image_url`?:optional, `source_url`?:optional |
| `gis_add_master_plan` | Register a housing-society/zone master plan as a rectified geo-layer. | `entity_type`:string, `entity_id`:string, `name`:string, `north`:number, `south`:number, `east`:number, `west`:number, `image_url`?:optional, `source_url`?:optional, `base_map`?:optional, `description`?:optional, `layer_type`?:string="master_plan", `style`?:optional |
| `gis_add_road_network` | Register a custom routable road network from ``ways`` (polylines). | `name`:string, `ways`?:optional, `description`?:optional |
| `gis_add_zone` | Add a zone polygon layer (residential / commercial / industrial / mixed). | `entity_type`:string, `entity_id`:string, `name`:string, `coordinates`:array<array>, `zone_type`?:string="residential", `style`?:optional |
| `gis_analysis_assumptions` | Show the planning assumptions used for cost / population / economic estimates. | — |
| `gis_area_analysis` | Full analysis of a city / scheme / block: area, properties, population, cost, economics. | `entity_type`:string, `entity_id`:string |
| `gis_area_report` | Printable HTML report for an area: area, valuation, population, development cost, economics. | `entity_type`:string, `entity_id`:string, `include_map`?:boolean=true, `include_outlook`?:boolean=false, `include_news`?:boolean=false, `years`?:integer=5, `lang`?:string="en", `theme`?:string="auto" |
| `gis_bearing` | Compass bearing and distance from point 1 to point 2. | `lat1`:number, `lon1`:number, `lat2`:number, `lon2`:number |
| `gis_buffer_geometry` | Buffer any GeoJSON geometry (Point/Line/Polygon) by ``distance_m`` metres. | `geometry`:object, `distance_m`:number, `segments`?:integer=48 |
| `gis_buffer_point` | Create a circular buffer polygon around a point. | `latitude`:number, `longitude`:number, `radius_m`:number, `segments`?:integer=72 |
| `gis_cost_development_analysis` | Cost & development perspective: GDV, cost build-up, developer profit, ROI, break-even, | `entity_type`:string, `entity_id`:string, `sale_uplift`?:number=0.0, `build_years`?:integer=3 |
| `gis_delete_layer` | Delete a GIS layer. | `layer_id`:string |
| `gis_destination` | Project a point by a bearing and distance (metres). | `latitude`:number, `longitude`:number, `bearing`:number, `distance_m`:number |
| `gis_development_cost` | Development-cost estimate (land development, infrastructure, construction) for an entity. | `entity_type`:string, `entity_id`:string |
| `gis_distance_matrix` | Straight-line distances from a point to several properties, sorted nearest first. | `origin_latitude`:number, `origin_longitude`:number, `property_ids`:array<string> |
| `gis_economic_impact` | Economic-impact estimate (investment, output, jobs, tax, rental) for an entity. | `entity_type`:string, `entity_id`:string |
| `gis_export_geojson` | Export an entity's properties + GIS layers as one GeoJSON FeatureCollection. | `entity_type`:string, `entity_id`:string |
| `gis_export_kml` | Export an entity's layers + properties as KML (open in Google Earth). | `entity_type`:string, `entity_id`:string |
| `gis_feature_table` | Prepare per-area features (a metric per scheme/block) for thematic maps and charts. | `scope_type`:string, `scope_id`:string, `metric`?:string="population" |
| `gis_forecast` | Future predictions for an area from development, social, economic and political factors, | `entity_type`:string, `entity_id`:string, `years`?:integer=5 |
| `gis_get_base_map` | Get one base map definition (tile URL template, attribution, max zoom). | `base_map_id`:string |
| `gis_get_layer` | Get a GIS layer by id (includes its full GeoJSON). | `layer_id`:string |
| `gis_list_base_maps` | List available base maps (Google Earth-style imagery + open alternatives). | — |
| `gis_list_layers` | List GIS layers, optionally filtered by entity and/or layer type. | `entity_type`?:optional, `entity_id`?:optional, `layer_type`?:optional |
| `gis_list_master_plans` | List master-plan layers (and other registered plan layers). | `entity_type`?:optional, `entity_id`?:optional |
| `gis_list_road_networks` | List the road networks currently available for routing. | — |
| `gis_map_preview` | Return a self-contained HTML map (Leaflet) with base-map switcher + overlays. | `entity_type`:string, `entity_id`:string, `base_map`?:optional, `include_properties`?:boolean=true, `include_news`?:boolean=false, `include_poi`?:boolean=false, `lang`?:string="en", `theme`?:string="auto", `lang_links`?:boolean=true |
| `gis_market_factors` | Development / social / economic / political / regulatory factor scores for an area. | `entity_type`:string, `entity_id`:string |
| `gis_outlook_report` | Printable HTML outlook report: area + valuation + cost/development + predictions | `entity_type`:string, `entity_id`:string, `years`?:integer=5, `include_map`?:boolean=true, `include_news`?:boolean=true, `lang`?:string="en", `theme`?:string="auto" |
| `gis_point_in_layer` | Test whether a point falls inside a layer's polygon. | `layer_id`:string, `latitude`:number, `longitude`:number |
| `gis_point_map` | Interactive Leaflet map centred on a point, optionally plotting nearby properties and POIs. | `latitude`:number, `longitude`:number, `radius_km`?:number=2.0, `zoom`?:integer=14, `base_map`?:optional, `include_properties`?:boolean=true, `include_poi`?:boolean=false, `title`?:string="Real Estate Portal", `lang`?:string="en", `theme`?:string="auto", `lang_links`?:boolean=true |
| `gis_polygon_analysis` | Full analysis of an arbitrary polygon: area, properties, population, cost, economics. | `coordinates`:array<array>, `name`?:string="Custom area", `total_units`?:optional |
| `gis_polygon_area` | Geodesic area of a polygon ([lat, lon] pairs) in sqm, sqft, marla and kanal. | `coordinates`:array<array> |
| `gis_polygon_centroid` | Centroid of a polygon ([lat, lon] pairs). | `coordinates`:array<array> |
| `gis_population_estimate` | Population, households and density estimate for an entity. | `entity_type`:string, `entity_id`:string |
| `gis_properties_in_bounds` | Find properties inside a lat/lon bounding box. | `south`:number, `west`:number, `north`:number, `east`:number, `limit`?:integer=50 |
| `gis_properties_in_polygon` | Find properties inside an arbitrary polygon. ``coordinates`` are [lat, lon] pairs. | `coordinates`:array<array>, `limit`?:integer=50 |
| `gis_ring_analysis` | Concentric-ring (annulus) accessibility analysis around a point. | `latitude`:number, `longitude`:number, `radii_km`:array<number>, `use_type`?:optional |
| `gis_road_classes` | Road classes with their per-mode speeds (0 = the mode may not use that class). | — |
| `gis_route` | Best route (plus alternatives) between two points by ``walk`` / ``bike`` / ``drive``. | `origin_latitude`:number, `origin_longitude`:number, `destination_latitude`:number, `destination_longitude`:number, `mode`?:string="drive", `alternatives`?:integer=2, `traffic_factor`?:optional, `city`?:optional, `scheme`?:optional, `network`?:optional, `origin_label`?:optional, `destination_label`?:optional |
| `gis_route_compare` | Compare every travel mode (on foot / bicycle / motor car) between two points. | `origin_latitude`:number, `origin_longitude`:number, `destination_latitude`:number, `destination_longitude`:number, `modes`?:optional, `city`?:optional, `scheme`?:optional, `network`?:optional |
| `gis_route_map` | Interactive map (HTML) of the best route and its alternatives, by foot or car. | `origin_latitude`:number, `origin_longitude`:number, `destination_latitude`:number, `destination_longitude`:number, `mode`?:string="drive", `alternatives`?:integer=2, `include_compare`?:boolean=true, `ticker`?:boolean=false, `base_map`?:optional, `city`?:optional, `scheme`?:optional, `network`?:optional, `lang`?:string="en", `theme`?:string="auto" |
| `gis_route_matrix` | Distance/time matrix between a set of POIs (by id/name) or raw ``[lat, lon]`` points. | `poi_ids`?:optional, `coordinates`?:optional, `mode`?:string="drive", `city`?:optional, `scheme`?:optional, `network`?:optional |
| `gis_scenario_analysis` | Compare the optimistic / base / pessimistic / stress scenarios side by side. | `entity_type`:string, `entity_id`:string, `years`?:integer=5 |
| `gis_thematic_map` | Choropleth (thematic) map HTML for a metric across a city's schemes or a scheme's blocks. | `scope_type`:string, `scope_id`:string, `metric`?:string="population", `palette`?:string="blues", `classes`?:integer=5, `base_map`?:optional, `lang`?:string="en", `theme`?:string="auto" |
| `gis_travel_modes` | The available travel modes (on foot, bicycle, motor car) and their road speeds. | — |
| `gis_update_layer` | Update a GIS layer (visibility, style, base map, geometry, ...). | `layer_id`:string, `name`?:optional, `description`?:optional, `base_map`?:optional, `visible`?:optional, `opacity`?:optional, `z_index`?:optional, `style`?:optional, `geojson`?:optional |

## hierarchy

26 tools.

| Tool | Purpose | Parameters |
| --- | --- | --- |
| `add_big_project` | Create a big project (mall, tower, mixed-use, compound, plaza, office complex). | `name`:string, `city_id`:string, `project_type`?:string="mall", `description`?:optional, `status`?:string="planned", `floor_count`?:integer=0, `total_area`?:optional, `total_units`?:optional, `scheme_id`?:optional, `block_zone_area_id`?:optional, `latitude`?:optional, `longitude`?:optional, `developer`?:optional, `start_date`?:optional, `completion_date`?:optional |
| `add_block_zone_area` | Create a block/zone/area inside a housing scheme. | `name`:string, `scheme_id`:string, `description`?:optional, `area_type`?:string="residential" |
| `add_city` | Create a city. | `name`:string, `state`?:optional, `country`?:string="Pakistan", `latitude`?:optional, `longitude`?:optional, `description`?:optional |
| `add_housing_scheme` | Create a housing scheme/society inside a city (with optional development details). | `name`:string, `city_id`:string, `description`?:optional, `total_units`?:optional, `established_year`?:optional, `developer`?:optional, `latitude`?:optional, `longitude`?:optional, `development_status`?:optional, `approval_authority`?:optional, `possession_status`?:optional, `utilities`?:optional, `population`?:optional |
| `add_project_amenity` | Add an amenity to a big project. | `project_id`:string, `amenity`:string |
| `add_project_floor_plan` | Attach a floor plan to a big project. | `project_id`:string, `floor_plan_url`:string |
| `add_project_map` | Attach a map/location image to a big project. | `project_id`:string, `map_url`:string |
| `add_project_multimedia` | Attach multimedia (e.g. video/VR/drone) to a big project. | `project_id`:string, `media_type`:string, `url`:string |
| `add_property` | Create a property. Areas auto-derive between total_area / marla / kanal. | `title`:string, `price`:number, `city_id`:string, `description`?:optional, `use_type`?:string="residential", `category`?:string="house", `scheme_id`?:optional, `block_zone_area_id`?:optional, `total_area`?:optional, `marla_area`?:optional, `kanal_area`?:optional, `bedrooms`?:optional, `bathrooms`?:optional, `balconies`?:optional, `floors`?:optional, `street_address`?:optional, `plot_number`?:optional, `sector`?:optional, `landmark`?:optional, `latitude`?:optional, `longitude`?:optional, `featured`?:boolean=false, `agent_id`?:optional, `owner_user_id`?:optional, `amenities`?:optional |
| `delete_big_project` | Delete a big project by id. | `project_id`:string |
| `delete_property` | Delete a property by id. | `property_id`:string |
| `get_big_project_by_id` | Fetch a big project by id. | `project_id`:string |
| `get_city_coordinates` | Get the coordinates of a city. | `city`:string |
| `get_city_details` | Get a single city's full record plus its schemes and property count. | `city`:string |
| `get_hierarchy` | Return the full City -> Scheme -> Block -> Property tree with counts. | — |
| `get_memory_analytics` | Summarise the memory layers (cache size, searches, views, favourites). | — |
| `get_property_by_id` | Fetch one property, including its hierarchy context and neighbours. | `property_id`:string |
| `get_property_distance` | Distance between two properties (both must have coordinates). | `property_id_1`:string, `property_id_2`:string |
| `list_big_projects` | List big projects, filtered by city and/or type. | `city`?:optional, `project_type`?:optional |
| `list_blocks` | List blocks/zones/areas, optionally filtered by scheme (id or name). | `scheme`?:optional |
| `list_cities` | List every city in the portal with its coordinates and child counts. | — |
| `list_owned_properties` | List the properties a portal account has published (newest first). | `owner_user_id`:string, `status`?:optional, `limit`?:integer=100 |
| `list_schemes` | List housing schemes/societies, optionally filtered by city (id or name). | `city`?:optional |
| `update_big_project` | Update editable fields of a big project. | `project_id`:string, `name`?:optional, `description`?:optional, `status`?:optional, `floor_count`?:optional, `total_area`?:optional, `total_units`?:optional, `occupancy_rate`?:optional, `developer`?:optional, `completion_date`?:optional, `total_parking_spaces`?:optional, `total_retail_space`?:optional, `total_office_space`?:optional, `total_residential_units`?:optional |
| `update_housing_scheme` | Update a housing scheme's details, e.g. its development / approval / possession status. | `scheme_id`:string, `description`?:optional, `total_units`?:optional, `established_year`?:optional, `developer`?:optional, `latitude`?:optional, `longitude`?:optional, `development_status`?:optional, `approval_authority`?:optional, `possession_status`?:optional, `utilities`?:optional, `population`?:optional |
| `update_property` | Update editable fields of a property (only the provided fields change). | `property_id`:string, `title`?:optional, `description`?:optional, `price`?:optional, `use_type`?:optional, `category`?:optional, `status`?:optional, `bedrooms`?:optional, `bathrooms`?:optional, `total_area`?:optional, `marla_area`?:optional, `kanal_area`?:optional, `latitude`?:optional, `longitude`?:optional, `featured`?:optional, `amenities`?:optional |

## images

4 tools.

| Tool | Purpose | Parameters |
| --- | --- | --- |
| `image_delete` | Delete an image by index from an entity's gallery. | `entity_type`:string, `entity_id`:string, `image_index`?:integer=0 |
| `image_list` | List images for one entity or the whole entity type. | `entity_type`:string, `entity_id`?:optional |
| `image_set_primary` | Mark one image as the primary image for an entity. | `entity_type`:string, `entity_id`:string, `image_index`?:integer=0 |
| `image_store` | Store an image URL against any entity (city, scheme, block, property, bigproject, agent). | `entity_type`:string, `entity_id`:string, `image_url`:string, `description`?:optional, `is_primary`?:boolean=false |

## intelligence

10 tools.

| Tool | Purpose | Parameters |
| --- | --- | --- |
| `buyer_affordability` | Monthly payment, property tax, holding costs and a debt-to-income verdict for a price. | `price`:number, `down_payment_share`?:number=0.25, `annual_rate`?:optional, `years`?:optional, `monthly_income`?:optional, `property_tax_rate`?:number=0.01, `holding_monthly`?:number=0.0, `other_debt_monthly`?:number=0.0 |
| `buyer_anomaly_scan` | Z-score the market: surface listings priced below their area average (bargains) | `city`?:optional, `category`?:optional, `use_type`?:optional, `threshold`?:number=1.0 |
| `buyer_parse_requirement` | Parse a natural-language buyer brief into a structured requirement. | `text`:string |
| `buyer_recommend` | Conversational buyer agent: parse the brief, then rank live listings on weighted | `text`?:optional, `limit`?:integer=8, `city`?:optional, `category`?:optional, `use_type`?:optional, `max_price`?:optional |
| `buyer_report` | Render the conversational buyer agent's brief, shortlist and bargain scan as HTML. | `text`:string, `lang`?:string="en", `theme`?:string="auto" |
| `create_listing_draft` | Draft a complete listing kit for a property. | `property_id`:string, `tone`?:string="professional", `lang`?:string="en" |
| `seller_cma` | Seller pricing agent: adjusted comparable-market analysis for a property. | `property_id`:string, `comp_ids`?:optional |
| `seller_marketing_assets` | Generate a full marketing kit for a listing: headline, description, bullets, | `property_id`:string, `tone`?:string="professional", `lang`?:string="en" |
| `seller_net_proceeds` | A seller's net cash after commission, selling costs, mortgage payoff and capital gains. | `price`:number, `commission_rate`?:number=0.02, `other_cost_rate`?:number=0.01, `mortgage_payoff`?:number=0.0, `cost_basis`?:optional, `capital_gains_rate`?:optional |
| `seller_report` | Render a seller CMA + net-proceeds + marketing HTML report. | `property_id`:string, `lang`?:string="en", `theme`?:string="auto" |

## investment

5 tools.

| Tool | Purpose | Parameters |
| --- | --- | --- |
| `investment_analysis` | Price/sqft, price/marla and market comparison for a property. | `property_id`:string |
| `investment_portfolio_alerts` | Proactive investor alerts: exit windows closing, refinance opportunities and | `holdings`?:optional, `interest_rate`?:number=0.18, `rent_index_change`?:number=0.0, `supply_change`?:number=0.0, `market_heat`?:number=0.5 |
| `investment_report` | Render the investment screener's shortlist, alerts and GTK as an HTML report. | `city`?:optional, `rental_yield`?:number=0.045, `min_cap_rate`?:number=0.025, `lang`?:string="en", `theme`?:string="auto" |
| `investment_screen` | Agentic Investment Screener: underwrite the live listing book against criteria and | `city`?:optional, `category`?:optional, `rental_yield`?:number=0.045, `min_cap_rate`?:optional, `min_dscr`?:optional, `max_price`?:optional, `down_payment_share`?:number=0.25, `loan_rate`?:number=0.16, `loan_years`?:integer=20, `hold_years`?:integer=10, `limit`?:integer=10 |
| `investment_underwrite` | Underwrite a deal: NOI, debt service, DSCR, cap rate, cash-on-cash, after-tax cash | `purchase_price`:number, `monthly_rent`?:number=0.0, `annual_rent`?:optional, `down_payment_share`?:number=0.25, `loan_rate`?:optional, `loan_years`?:integer=20, `vacancy_rate`?:number=0.05, `operating_expense_rate`?:number=0.3, `appreciation_rate`?:number=0.06, `exit_cap_rate`?:number=0.07, `hold_years`?:integer=10, `tax_rate`?:number=0.0 |

## leasing

11 tools.

| Tool | Purpose | Parameters |
| --- | --- | --- |
| `leasing_collection` | Rent-collection board: active leases, arrears and total outstanding from the ledger. | — |
| `leasing_funnel` | Leasing funnel: inquiries, auto-handled share, applications and channel/intent mix. | — |
| `leasing_inquiries` | Log of handled leasing inquiries (optionally filtered by unit or intent). | `unit_id`?:optional, `intent`?:optional |
| `leasing_inquiry` | Autonomous leasing agent: classify a tenant inquiry, draft a reply and decide whether | `message`:string, `unit_id`?:optional, `channel`?:string="web_chat", `lang`?:string="en" |
| `leasing_portal` | Render the **Autonomous Leasing wing** portal page (HTML) with a live rent-floor and | `lang`?:string="en", `theme`?:string="auto" |
| `leasing_renewals` | Renewal Agent: recommend renewal rents and retention actions for every active lease. | `uplift`?:number=0.08, `hold_rent_if_risky`?:boolean=true |
| `leasing_rent_floor` | The minimum rent that keeps a unit cash-flow positive (holding cost + margin). | `monthly_holding_cost`:number, `margin`?:optional |
| `leasing_screen_application` | Screen a rental application: income-to-rent, references, credit proxy and employment | `applicant`:string, `monthly_income`:number, `unit_id`?:optional, `employment`?:string="salaried", `references_count`?:integer=0, `credit_proxy`?:integer=70, `occupants`?:integer=1, `pets`?:boolean=false, `move_in_days`?:integer=15 |
| `leasing_unit` | One rental unit by id. | `unit_id`:string |
| `leasing_unit_create` | Register a rental unit (with monthly holding cost so a rent floor can be enforced). | `title`:string, `rent`?:number=0.0, `city`?:optional, `scheme`?:optional, `bedrooms`?:optional, `area`?:optional, `deposit`?:number=0.0, `monthly_holding_cost`?:number=0.0, `amenities`?:optional |
| `leasing_units` | Rental units available to the autonomous leasing agent (net of registered units and | `status`?:optional, `city`?:optional, `limit`?:integer=50 |

## maintenance

27 tools.

| Tool | Purpose | Parameters |
| --- | --- | --- |
| `maintenance_component` | One asset component by key (e.g. ``roof_waterproofing``, ``hvac``). | `key`:string |
| `maintenance_components` | Maintainable building components with service life, replacement cost, criticality, | `category`?:optional |
| `maintenance_condition` | Score a building's condition (1–5 per area) into a band with recommended actions. | `age_years`:number, `property_type`?:string="house", `ratings`?:optional |
| `maintenance_defect` | One defect by key (e.g. ``roof_seepage``, ``structural_cracks``). | `key`:string |
| `maintenance_defects` | Defect catalogue: symptoms, causes, severity, diagnosis, repair method, cost band, | `category`?:optional, `severity`?:optional, `component`?:optional |
| `maintenance_estimate` | Annual routine-maintenance cost estimate with a category breakdown and the | `covered_area`:number, `property_type`?:string="house", `tier`?:string="standard", `quality`?:string="standard", `age_years`?:number=0.0, `city`?:optional, `floors`?:integer=1 |
| `maintenance_guidelines` | Maintenance best-practice, compliance, safety and management guidelines. | `category`?:optional |
| `maintenance_impact` | How condition and maintenance move market value, rent, yield, occupancy and tenant | `market_value`:number, `monthly_rent`:number, `covered_area`?:number=1000.0, `current_condition`?:string="fair", `tier`?:string="standard" |
| `maintenance_inspection` | Inspection checklists by area (structural, envelope, MEP, finishes, safety). | `area`?:optional |
| `maintenance_lifecycle` | Multi-year capital-replacement schedule (a reserve study) with inflated costs. | `covered_area`:number, `property_type`?:string="house", `quality`?:string="standard", `age_years`?:number=0.0, `city`?:optional, `years`?:integer=30 |
| `maintenance_overview` | Counts, category breakdowns and configuration for the maintenance wing. | — |
| `maintenance_plan_get` | One saved maintenance plan by id. | `plan_id`:string |
| `maintenance_plan_save` | Compute an annual-maintenance estimate and persist it as a maintenance plan. | `title`:string, `covered_area`:number, `property_type`?:string="house", `tier`?:string="standard", `quality`?:string="standard", `age_years`?:number=0.0, `city`?:optional, `notes`?:optional |
| `maintenance_plans` | Saved maintenance plans. | `property_type`?:optional |
| `maintenance_portal` | Render the **Maintenance wing** portal page (HTML) — components, services, defects, | `lang`?:string="en", `theme`?:string="auto" |
| `maintenance_repair_estimate` | Estimate the cost to repair a known defect over a given quantity. | `defect`:string, `quantity`?:number=1.0, `city`?:optional |
| `maintenance_repair_or_replace` | Decide between repairing and replacing a component, with a 5-year cost comparison. | `component`:string, `age_years`:number, `condition`?:optional, `covered_area`?:number=1000.0, `quality`?:string="standard", `city`?:optional |
| `maintenance_report` | Render a printable **maintenance report** (HTML): annual cost, reserve, preventive | `covered_area`:number, `property_type`?:string="house", `tier`?:string="standard", `quality`?:string="standard", `age_years`?:number=0.0, `city`?:optional, `lang`?:string="en", `theme`?:string="auto" |
| `maintenance_reserve` | Annual sinking-fund (reserve) contribution to replace components at end of life. | `covered_area`:number, `property_type`?:string="house", `quality`?:string="standard", `age_years`?:number=0.0, `city`?:optional |
| `maintenance_schedule` | A periodic preventive-maintenance calendar for a property. | `property_type`?:string="house", `age_years`?:number=0.0, `horizon_months`?:integer=12 |
| `maintenance_service` | One maintenance service by key (e.g. ``ac_service``, ``waterproofing``). | `key`:string |
| `maintenance_services` | Maintenance services & trades with unit cost bands, emergency flags and response | `category`?:optional, `emergency`?:optional |
| `maintenance_warranty` | Warranty terms by component (duration, cover and exclusions). | `component`?:optional |
| `maintenance_work_order_create` | Raise a maintenance work order (a service request / job). | `title`:string, `property_type`?:string="house", `component`?:optional, `defect`?:optional, `priority`?:string="routine", `description`?:optional, `estimated_cost`?:number=0.0, `assignee`?:optional |
| `maintenance_work_order_get` | One maintenance work order by id. | `wo_id`:string |
| `maintenance_work_order_update` | Update a maintenance work order (status, priority, assignee, cost). | `wo_id`:string, `status`?:optional, `priority`?:optional, `assignee`?:optional, `estimated_cost`?:optional, `description`?:optional |
| `maintenance_work_orders` | List maintenance work orders, filtered by status / priority / component. | `status`?:optional, `priority`?:optional, `component`?:optional |

## market

1 tools.

| Tool | Purpose | Parameters |
| --- | --- | --- |
| `get_market_intelligence` | Regional market intelligence — pricing, factor index, news momentum and a forecast. | `region`?:optional, `years`?:integer=5 |

## marketing

12 tools.

| Tool | Purpose | Parameters |
| --- | --- | --- |
| `marketing_campaign_plan` | Plan a multichannel campaign: budget allocation, a day-by-day schedule and KPIs. | `objective`:string, `budget`:number, `channels`:array<string>, `days`?:integer=14, `audience`?:optional |
| `marketing_channels` | Cross-channel lead sources and their qualification quality, plus the content kinds. | — |
| `marketing_content_approve` | Human approval gate for a generated content asset. | `asset_id`:string, `approver`?:string="user" |
| `marketing_content_assets` | Content assets awaiting approval, approved or published. | `status`?:optional |
| `marketing_funnel` | Lead funnel: counts by stage, band and channel with conversion metrics. | — |
| `marketing_generate_content` | Generate a marketing content asset (listing description, social post, reel script, | `kind`?:string="market_report", `property_id`?:optional, `tone`?:string="professional", `lang`?:string="en", `topic`?:optional |
| `marketing_portal` | Render the **AI Marketing Conductor wing** portal page (HTML) with routing, funnel and | `lang`?:string="en", `theme`?:string="auto" |
| `marketing_qualify` | Qualify a CRM lead: score (0–100), band, reasons and recommended action; syncs the | `lead_id`:string |
| `marketing_reengagement` | Re-engagement Agent: mine dormant and previously-lost leads, flag false negatives and | `inactive_days`?:optional, `min_score`?:optional |
| `marketing_route_add` | Add a lead-routing rule. ``match`` may carry city, language, source, use_type, | `name`:string, `match`:object, `assign_to_agent_id`?:optional, `queue`?:string="general", `priority`?:integer=100, `sla_hours`?:integer=4 |
| `marketing_route_lead` | Route a CRM lead to the best-matching rule, queue, agent and SLA. | `lead_id`:string |
| `marketing_routes` | Lead-routing rules (postcode/city/language/price/source → agent, queue and SLA). | — |

## memory

3 tools.

| Tool | Purpose | Parameters |
| --- | --- | --- |
| `memory_clear` | Clear every memory layer. | — |
| `memory_retrieve` | Retrieve a value from long-term memory (favorites, views, preferences) or near cache. | `key`:string |
| `memory_store` | Manage memory. operations: add_near \| add_favorite \| set_preference \| clear. | `operation`:string, `key`?:optional, `value`?:optional |

## messaging

66 tools.

| Tool | Purpose | Parameters |
| --- | --- | --- |
| `msg_action` | One tracked action with its updates and overdue flag. | `action_id`:string, `user_id`:string |
| `msg_action_items` | Extract action items from a conversation (optionally create tracked actions). | `conversation_id`:string, `user_id`:string, `limit`?:integer=100, `create`?:boolean=false, `owner_default`?:optional |
| `msg_actions` | List tracked actions the user can see (filter by conversation, owner, status, kind). | `user_id`:string, `conversation_id`?:optional, `owner_id`?:optional, `status`?:optional, `kind`?:optional, `overdue_only`?:boolean=false |
| `msg_add_member` | Add (or re-role) a member of a conversation. | `conversation_id`:string, `member_id`:string, `actor_id`?:optional, `role`?:string="member" |
| `msg_archive_conversation` | Archive or restore a conversation (owner/admin only). | `conversation_id`:string, `user_id`:string, `archived`?:boolean=true |
| `msg_attach` | Register a file reference (controlled storage or an existing portal record). | `conversation_id`:string, `uploaded_by`:string, `filename`:string, `kind`?:optional, `size_bytes`?:integer=0, `mime`?:optional, `storage_key`?:optional, `source_url`?:optional, `sensitivity`?:optional, `linked_type`?:optional, `linked_id`?:optional |
| `msg_attachment_kinds` | Attachment kinds, accepted extensions and default sensitivity. | `kind`?:optional |
| `msg_attachment_link` | Mint a signed, expiring, permission-checked download link for an attachment. | `attachment_id`:string, `user_id`:string, `ttl_minutes`?:optional |
| `msg_attachment_resolve` | Verify a signed attachment link (signature + expiry) and re-check access. | `token`:string, `user_id`?:optional |
| `msg_attachments` | List a conversation's shared files (references, never embedded content). | `conversation_id`:string, `user_id`:string, `kind`?:optional, `sensitivity`?:optional |
| `msg_audit` | The messaging audit trail of important actions (access, files, moderation). | `limit`?:integer=100, `action`?:optional, `actor_id`?:optional, `target_type`?:optional |
| `msg_categories` | Notification categories with their default delivery channels and urgency. | `category`?:optional |
| `msg_channels` | Default team channels (Sales, Property Verification, GIS & Mapping, Support, Management). | `channel_key`?:optional |
| `msg_complete_action` | Mark an action done and notify its creator. | `action_id`:string, `user_id`:string, `note`?:optional |
| `msg_conversation` | One conversation with members, pins, unread count and full context. | `conversation_id`:string, `user_id`:string |
| `msg_conversation_context` | What a conversation is tied to: property, pinned messages, actions, attachments. | `conversation_id`:string, `user_id`?:optional |
| `msg_conversation_digest` | Recent-activity digest for a conversation over a window. | `conversation_id`:string, `user_id`:string, `days`?:integer=7 |
| `msg_conversations` | List a user's conversations with unread counts, newest activity first. | `user_id`:string, `kind`?:optional, `include_archived`?:boolean=false, `property_id`?:optional, `channel_key`?:optional |
| `msg_create_action` | Turn a message into a tracked action (task/approval/verification/request), optional CRM task. | `conversation_id`:string, `created_by`:string, `title`:string, `kind`?:string="task", `message_id`?:optional, `detail`?:optional, `owner_id`?:optional, `due_on`?:optional, `property_id`?:optional, `create_crm_task`?:boolean=false |
| `msg_create_conversation` | Create a direct / group / channel / property conversation and seed its members. | `kind`?:string="group", `title`?:string="", `created_by`?:optional, `participants`?:optional, `channel_key`?:optional, `property_id`?:optional, `topic`?:optional, `restricted`?:optional, `roles_allowed`?:optional, `retention_days`?:optional, `announcement`?:optional |
| `msg_delete_message` | Soft-delete a message (author or conversation admin). | `message_id`:string, `user_id`:string, `reason`?:optional |
| `msg_direct` | Find or create the 1-to-1 conversation between two users. | `user_a`:string, `user_b`:string |
| `msg_dispatch` | Drain the notification queue into the outbox (the background-worker seam). | `user_id`?:optional, `limit`?:integer=200, `force`?:boolean=false |
| `msg_edit_message` | Edit a message (author only, within the edit window). | `message_id`:string, `user_id`:string, `body`:string |
| `msg_mark_all_notifications_read` | Mark every notification read for a user. | `user_id`:string |
| `msg_mark_read` | Mark a conversation read up to a sequence number (defaults to the latest). | `conversation_id`:string, `user_id`:string, `up_to_seq`?:optional |
| `msg_members` | Members of a conversation with roles, presence and read positions. | `conversation_id`:string, `user_id`?:optional |
| `msg_message` | One message with its attachments, reactions, read receipts and replies. | `message_id`:string, `user_id`:string |
| `msg_messages` | Page through a conversation's messages (or one thread), oldest to newest. | `conversation_id`:string, `user_id`:string, `limit`?:integer=50, `before_seq`?:optional, `thread_id`?:optional, `include_deleted`?:boolean=false |
| `msg_moderate_report` | Resolve a report: dismiss, delete the message, mute the author or escalate. | `report_id`:string, `actor_id`:string, `action`:string, `note`?:optional |
| `msg_notifications` | A user's notifications (queue + delivered) with unread count. | `user_id`:string, `unread_only`?:boolean=false, `category`?:optional, `limit`?:integer=50 |
| `msg_outbox` | Delivered notifications with rendered e-mail and Telegram payloads. | `channel`?:optional, `user_id`?:optional, `limit`?:integer=100 |
| `msg_overview` | Team-messaging overview: config, channels, categories, counts and rollout plan. | — |
| `msg_pin_message` | Pin or unpin a message in its conversation. | `message_id`:string, `user_id`:string, `pinned`?:boolean=true |
| `msg_portal` | The Team Messaging & Notifications wing as a printable HTML page. | `lang`?:string="en", `theme`?:string="auto" |
| `msg_post` | Post a message (checked for membership, length and rate limit); notifies recipients. | `conversation_id`:string, `author_id`:string, `body`?:string="", `message_type`?:string="text", `parent_id`?:optional, `mentions`?:optional, `attachment_ids`?:optional, `property_id`?:optional |
| `msg_preferences` | A user's notification preferences, quiet hours, digest mode and Telegram state. | `user_id`:string |
| `msg_presence_heartbeat` | Heartbeat a user's presence without spamming the audit trail. | `user_id`:string, `presence`?:optional |
| `msg_profiles` | Team directory of messaging profiles (filter by presence, role or text). | `presence`?:optional, `role`?:optional, `query`?:optional |
| `msg_property_thread` | Get or create the internal discussion panel for a property record. | `property_id`:string, `created_by`?:optional, `title`?:optional |
| `msg_purge_retention` | Apply the retention policy (soft-delete past the window; pinned exempt). | `dry_run`?:boolean=true, `retention_days`?:optional, `actor_id`?:optional |
| `msg_react` | Toggle an emoji reaction on a message. | `message_id`:string, `user_id`:string, `emoji`:string |
| `msg_read_notification` | Mark one notification read. | `notification_id`:string, `user_id`:string |
| `msg_read_receipts` | Who has read a message (read receipts). | `message_id`:string, `user_id`:string |
| `msg_remove_member` | Remove a member from a conversation (audited access revocation). | `conversation_id`:string, `member_id`:string, `actor_id`?:optional, `reason`?:optional |
| `msg_report_message` | Report a message (spam, abuse, confidential leak, off-topic). | `message_id`:string, `reporter_id`:string, `reason`?:string="other", `detail`?:optional |
| `msg_reports` | Message reports and their status (spam-control queue). | `status`?:optional, `limit`?:integer=100 |
| `msg_retention_report` | Per-conversation retention picture: messages, pins and purgeable counts. | — |
| `msg_revoke_access` | Revoke a user's access to every conversation and unlink Telegram (staff leaving). | `user_id`:string, `actor_id`?:optional, `reason`?:optional |
| `msg_search` | Search messages across every conversation the user may access. | `user_id`:string, `query`?:string="", `conversation_id`?:optional, `property_id`?:optional, `mention`?:optional, `limit`?:integer=25 |
| `msg_set_preferences` | Update per-category channels, quiet hours, digest mode and Telegram opt-in. | `user_id`:string, `prefs`?:optional, `quiet_start`?:optional, `quiet_end`?:optional, `digest`?:optional, `telegram_opt_in`?:optional, `telegram_categories`?:optional |
| `msg_set_presence` | Set a user's presence (online/away/busy/offline) and stamp last-seen. | `user_id`:string, `presence`?:string="online" |
| `msg_statistics` | Aggregate messaging statistics for the portal dashboard. | — |
| `msg_summarize` | Rules-based extractive summary: participants, topics, keywords and salient lines. | `conversation_id`:string, `user_id`:string, `limit`?:integer=80 |
| `msg_telegram_alert` | Queue and dispatch a sanitised alert (short text + deep link, never documents). | `user_id`:string, `text`:string, `priority`?:string="normal", `conversation_id`?:optional, `message_id`?:optional |
| `msg_telegram_link` | Opt a user in: bind a Telegram chat id and the allowed notification categories. | `user_id`:string, `chat_id`:string, `username`?:optional, `categories`?:optional |
| `msg_telegram_link_code` | Mint a single-use /start code so a user can link their Telegram chat. | `user_id`:string |
| `msg_telegram_links` | Every Telegram link (optionally only the active ones). | `active_only`?:boolean=true |
| `msg_telegram_status` | Whether a user is linked to Telegram, which categories and the bot name. | `user_id`:string |
| `msg_telegram_unlink` | Unlink a user's Telegram chat and disable Telegram alerts. | `user_id`:string |
| `msg_telegram_update` | Process one inbound Telegram bot update (/start, /stop, /mute, /digest, /status). | `update`:object |
| `msg_thread` | The threaded replies to a message. | `message_id`:string, `user_id`:string, `limit`?:integer=100 |
| `msg_unread` | Unread totals overall and per conversation, plus mention count. | `user_id`:string |
| `msg_unread_summary` | Combined unread picture: conversations, mentions, notifications and open actions. | `user_id`:string |
| `msg_update_action` | Update an action's status, owner or due date and add a note. | `action_id`:string, `user_id`:string, `status`?:optional, `owner_id`?:optional, `due_on`?:optional, `note`?:optional |
| `msg_update_member` | Update a member's role, mute/pin state or notification level. | `conversation_id`:string, `member_id`:string, `actor_id`?:optional, `role`?:optional, `muted`?:optional, `pinned`?:optional, `notification_level`?:optional |

## news

5 tools.

| Tool | Purpose | Parameters |
| --- | --- | --- |
| `news_add` | Add a news / announcement item that impacts real-estate sentiment. | `title`:string, `source`:string, `category`?:string="market", `sentiment`?:string="neutral", `impact_score`?:number=0.0, `channel_type`?:string="news", `summary`?:optional, `url`?:optional, `city_id`?:optional, `scheme_id`?:optional, `tags`?:optional |
| `news_channels` | List news channels/sources with item counts and average impact. | — |
| `news_impact` | Aggregate news sentiment / impact for a market and how it feeds the outlook. | `city`?:optional, `scheme`?:optional, `days`?:integer=120 |
| `news_list` | List news items, filtered by category / city / scheme / sentiment / channel / recency. | `category`?:optional, `city`?:optional, `scheme`?:optional, `sentiment`?:optional, `channel_type`?:optional, `days`?:optional, `limit`?:integer=50 |
| `news_ticker` | Render a self-contained scrolling news-ticker (HTML) of real-estate-relevant headlines. | `category`?:optional, `city`?:optional, `scheme`?:optional, `limit`?:integer=25, `speed_seconds`?:number=70.0, `label`?:string="Real Estate News", `lang`?:string="en" |

## pmo

58 tools.

| Tool | Purpose | Parameters |
| --- | --- | --- |
| `pm_actions` | List action items (optionally for one project / one status). | `project_id`?:optional, `status`?:optional |
| `pm_add_action` | Add a meeting action item with an owner and due date. | `project_id`:string, `title`:string, `owner`?:optional, `due_on`?:optional, `priority`?:string="medium", `meeting`?:optional, `notes`?:optional |
| `pm_add_cost` | Record a committed or actual cost entry against a project. | `project_id`:string, `amount`:number, `category`?:string="other", `description`?:string="", `kind`?:string="actual", `date`?:optional, `vendor`?:optional, `invoice_ref`?:optional, `recorded_by`?:optional |
| `pm_add_inspection` | Record a stage inspection with a pass/fail checklist; updates the quality index. | `project_id`:string, `title`:string, `checklist`?:optional, `phase_key`?:optional, `area`?:optional, `inspector`?:optional, `date`?:optional, `status`?:string="open", `notes`?:optional |
| `pm_add_milestone` | Add a milestone (optionally linked to a task and a billable amount). | `project_id`:string, `name`:string, `planned_date`?:optional, `phase_key`?:optional, `task_id`?:optional, `weight`?:number=1.0, `billable_amount`?:number=0.0, `notes`?:optional |
| `pm_add_phase` | Add a weighted phase to a project's work-breakdown. | `project_id`:string, `name`:string, `key`?:optional, `weight`?:number=0.0, `order`?:optional, `planned_start`?:optional, `planned_end`?:optional |
| `pm_add_resource` | Register a team/trade resource with a day rate and capacity. | `name`:string, `role`?:string="engineer", `trade`?:optional, `day_rate`?:number=0.0, `capacity_pct`?:number=100.0, `skills`?:optional, `contact`?:optional |
| `pm_add_risk` | Add a RAID item (risk/issue/assumption/dependency) with probability and impact (1–5). | `project_id`:string, `title`:string, `kind`?:string="risk", `probability`?:integer=3, `impact`?:integer=3, `description`?:optional, `category`?:optional, `owner`?:optional, `mitigation`?:optional, `due_on`?:optional |
| `pm_add_task` | Add a task (duration in working days, finish-to-start predecessors). | `project_id`:string, `name`:string, `phase_key`?:optional, `duration_days`?:integer=1, `predecessors`?:optional, `assignee_id`?:optional, `weight`?:number=0.0, `cost_budget`?:number=0.0, `priority`?:string="medium", `wbs`?:optional, `notes`?:optional |
| `pm_alerts` | Exception-based alerts for one project or the whole portfolio. | `project_id`?:optional |
| `pm_apply_template` | Seed a project's weighted phases and a task work-breakdown from its type template. | `project_id`:string, `project_type`?:optional |
| `pm_assign` | Assign a resource to a task at a percentage of their capacity. | `task_id`:string, `resource_id`:string, `units_pct`?:number=100.0, `notes`?:optional |
| `pm_changes` | List a project's change requests with the approved cost/schedule impact. | `project_id`:string, `status`?:optional |
| `pm_close_action` | Close (or reopen) a meeting action item. | `action_id`:string, `status`?:string="done" |
| `pm_cost_status` | Cost control: baseline, approved variations, revised budget, commitments, actuals and forecast. | `project_id`:string |
| `pm_costs` | List a project's cost entries (filter by kind/category). | `project_id`:string, `kind`?:optional, `category`?:optional |
| `pm_create_project` | Register a project (optionally seeding its weighted phases and WBS template). | `name`:string, `project_type`?:string="construction", `description`?:optional, `city`?:optional, `scheme`?:optional, `client`?:optional, `manager_id`?:optional, `start_date`?:optional, `end_date`?:optional, `budget`?:number=0.0, `contract_value`?:number=0.0, `priority`?:string="medium", `status`?:string="planning", `tags`?:optional, `with_template`?:boolean=true |
| `pm_critical_path` | The critical path (zero-float chain) with its entries and the project duration. | `project_id`:string |
| `pm_decide_change` | Approve or reject a change request (approval moves the project's revised budget). | `change_id`:string, `approve`?:boolean=true, `by`?:optional, `note`?:optional |
| `pm_delete_project` | Delete a project and everything that belongs to it (tasks, costs, risks, logs …). | `project_id`:string |
| `pm_delete_task` | Delete a task and its resource allocations. | `task_id`:string |
| `pm_earned_value` | Earned-value analysis: PV, EV, AC, SV, CV, SPI, CPI, EAC, ETC, VAC and TCPI. | `project_id`:string, `as_of`?:optional |
| `pm_from_estimate` | Create a delivery project from a saved Construction-wing estimate (budget = build cost). | `estimate_id`:string, `name`?:optional, `city`?:optional, `start_date`?:optional, `contract_value`?:optional |
| `pm_gantt` | Gantt-ready rows (phase, task, start, finish, progress, critical) for a project. | `project_id`:string |
| `pm_health` | Schedule/cost/risk/quality RAG status and an overall health verdict. | `project_id`:string |
| `pm_inspections` | List a project's inspections and the aggregated quality index. | `project_id`:string, `status`?:optional |
| `pm_kpi` | The KPI scorecard for a project. | `project_id`:string |
| `pm_log_site` | Record a daily site diary entry (weather, manpower, plant, work, safety). | `project_id`:string, `date`?:optional, `weather`?:optional, `manpower`?:integer=0, `equipment`?:optional, `work_done`?:optional, `issues`?:optional, `safety_incidents`?:integer=0, `visitors`?:optional, `photos`?:optional, `by`?:optional |
| `pm_milestones` | List a project's milestones with forecast dates and slip. | `project_id`:string, `status`?:optional |
| `pm_monitoring` | Alias of the project-controls snapshot (health, KPI, progress, cost, EVM, alerts). | `project_id`:string |
| `pm_phase_templates` | Default weighted phase templates by project type (or all templates). | `project_type`?:optional |
| `pm_phases` | List a project's phases with normalised weights and progress. | `project_id`:string |
| `pm_portal` | The Projects & Monitoring (PMO) page as HTML: register, capabilities and alerts. | `lang`?:string="en", `theme`?:string="auto" |
| `pm_portfolio` | Rolled-up dashboard across every running project with portfolio SPI/CPI. | — |
| `pm_progress` | Current actual vs planned (duration-weighted) completion for a project. | `project_id`:string |
| `pm_project` | One project by id or code, with phase/task/milestone counts. | `project_id`:string |
| `pm_project_dashboard` | The full project-controls snapshot: health, KPI, progress, cost, EVM, alerts and risks. | `project_id`:string |
| `pm_project_report` | A full project status report as structured data (schedule, cost, EVM, risks, alerts). | `project_id`:string |
| `pm_project_types` | The supported project types, statuses and priorities. | — |
| `pm_projects` | List projects with progress and health (filter by status, type, city, manager, priority). | `status`?:optional, `project_type`?:optional, `city`?:optional, `manager_id`?:optional, `priority`?:optional, `limit`?:integer=50 |
| `pm_raise_change` | Raise a variation / change request with cost and schedule impact. | `project_id`:string, `title`:string, `description`?:optional, `reason`?:optional, `cost_impact`?:number=0.0, `schedule_impact_days`?:integer=0, `requested_by`?:optional, `status`?:string="submitted" |
| `pm_record_progress` | Record a dated progress update for a project. | `project_id`:string, `percent`:number, `note`?:optional, `by`?:optional, `manpower`?:integer=0, `weather`?:optional, `on`?:optional |
| `pm_report_html` | A printable project status report as (themed, bilingual) HTML. | `project_id`:string, `lang`?:string="en", `theme`?:string="auto" |
| `pm_resource_load` | Planned resource utilisation over a window, with over-allocation flags. | `project_id`?:optional, `window_start`?:optional, `window_end`?:optional |
| `pm_resources` | List resources (filter by trade; optionally active only). | `trade`?:optional, `active_only`?:boolean=false |
| `pm_risk_matrix` | The probability × impact risk matrix with the placed RAID items. | `project_id`?:optional |
| `pm_risks` | List RAID items with their score and band (sorted by score). | `project_id`?:optional, `kind`?:optional, `status`?:optional, `min_score`?:integer=0 |
| `pm_s_curve` | The planned-vs-actual S-curve (weekly cumulative completion) for a project. | `project_id`:string, `weeks`?:integer=52 |
| `pm_schedule` | Run the forward/backward pass: ES/EF, LS/LF, total float and the critical path. | `project_id`:string, `start_date`?:optional |
| `pm_site_logs` | List a project's site diary entries. | `project_id`:string, `limit`?:integer=30 |
| `pm_site_report` | A daily site report: the diary entry, progress, health and open alerts. | `project_id`:string, `on`?:optional |
| `pm_task` | One task by id, with its scheduled start/finish, float and critical flag. | `task_id`:string |
| `pm_tasks` | List tasks with their scheduled start/finish, float and critical flag. | `project_id`:string, `phase_key`?:optional, `status`?:optional, `assignee_id`?:optional |
| `pm_update_project` | Update a project's fields (name, status, priority, budget, dates, client, tags …). | `project_id`:string, `updates`:object |
| `pm_update_risk` | Update a RAID item (probability, impact, status, owner, mitigation …). | `risk_id`:string, `updates`:object |
| `pm_update_task` | Update a task (progress %, status, dates, duration, assignee, cost …). | `task_id`:string, `updates`:object |
| `pmo_capabilities` | The PMO capabilities grouped by category (planning, tracking, monitoring, governance). | — |
| `pmo_overview` | Counts, breakdowns and configuration for the whole PMO (project management) wing. | — |

## poi

13 tools.

| Tool | Purpose | Parameters |
| --- | --- | --- |
| `poi_accessibility_score` | Distance-decayed liveability / accessibility score (0-100) for an entity or a point. | `entity_type`?:optional, `entity_id`?:optional, `latitude`?:optional, `longitude`?:optional, `radius_km`?:number=3.0 |
| `poi_add` | Register a point of interest (school, hospital, mall, mosque, stop, park …). | `name`:string, `latitude`:number, `longitude`:number, `category`?:string="other", `subcategory`?:optional, `address`?:optional, `city_id`?:optional, `scheme_id`?:optional, `block_zone_area_id`?:optional, `rating`?:optional, `importance`?:number=1.0, `tags`?:optional, `source`?:string="manual" |
| `poi_categories` | Every POI category with its count, liveability weight and average rating. | — |
| `poi_delete` | Delete a point of interest. | `poi_id`:string |
| `poi_density` | POI mix and density (per km²) inside an entity's footprint. | `entity_type`:string, `entity_id`:string |
| `poi_get` | Fetch one point of interest by id. | `poi_id`:string |
| `poi_list` | List points of interest, filtered by category / city / scheme / free text. | `category`?:optional, `city`?:optional, `scheme`?:optional, `query`?:optional, `limit`?:integer=100 |
| `poi_map` | Self-contained HTML map of points of interest around an entity or a point. | `entity_type`?:optional, `entity_id`?:optional, `latitude`?:optional, `longitude`?:optional, `radius_km`?:number=2.0, `categories`?:optional, `limit`?:integer=60, `base_map`?:optional, `lang`?:string="en", `theme`?:string="auto" |
| `poi_nearby` | Points of interest within ``radius_km`` of a point, nearest first. | `latitude`:number, `longitude`:number, `radius_km`?:number=2.0, `category`?:optional, `limit`?:integer=50 |
| `poi_nearest` | The single nearest POI in every category (handy for a liveability panel). | `latitude`:number, `longitude`:number, `radius_km`?:number=25.0 |
| `poi_route` | Route between two points of interest (by id or name), on foot or by car. | `origin_poi`:string, `destination_poi`:string, `mode`?:string="drive", `alternatives`?:integer=2, `traffic_factor`?:optional, `network`?:optional |
| `poi_update` | Update a point of interest. | `poi_id`:string, `name`?:optional, `category`?:optional, `subcategory`?:optional, `latitude`?:optional, `longitude`?:optional, `address`?:optional, `rating`?:optional, `importance`?:optional, `tags`?:optional |
| `poi_within_polygon` | Points of interest inside a polygon (``[[lat, lon], ...]``). | `coordinates`:array<array>, `category`?:optional |

## portal

9 tools.

| Tool | Purpose | Parameters |
| --- | --- | --- |
| `portal_audit_log` | Unified activity trail: memory cache, authentication events and recent ledger postings. | `limit`?:integer=50 |
| `portal_catalog` | Full inventory of the MCP surface (tools / resources / templates / prompts), grouped. | `include_parameters`?:boolean=false, `group`?:optional |
| `portal_health` | Liveness snapshot: version, store counts and registered MCP surface size. | — |
| `portal_languages` | List the UI languages available for maps, reports and the ticker (code, name, text direction). | — |
| `portal_schema` | JSON schema for a portal model (city, property, deal, invoice, poi, aoi …) or the model list. | `model`?:optional |
| `portal_settings` | Read or edit runtime settings. | `action`?:string="get", `updates`?:optional |
| `portal_statistics` | Portfolio-wide statistics: inventory, valuation, area, POIs and finance in one view. | — |
| `portal_strings` | Return the localisation dictionary for a language (English source string -> translation). | `lang`?:string="en" |
| `portal_themes` | List the UI themes (``auto`` / ``light`` / ``dark``) and the CSS custom properties each one sets. | — |

## rag

1 tools.

| Tool | Purpose | Parameters |
| --- | --- | --- |
| `rag_search` | Natural-language retrieval over properties, schemes and big projects. | `query`:string, `top_k`?:integer=5 |

## search

2 tools.

| Tool | Purpose | Parameters |
| --- | --- | --- |
| `search_nearby_properties` | Find properties within `radius_km` of a point, sorted by distance. | `latitude`:number, `longitude`:number, `radius_km`?:number=5.0, `use_type`?:optional, `category`?:optional, `max_price`?:optional, `limit`?:integer=20 |
| `search_properties` | Search properties with hierarchical and numeric filters. | `city`?:optional, `scheme`?:optional, `use_type`?:optional, `category`?:optional, `min_price`?:optional, `max_price`?:optional, `bedrooms`?:optional, `min_marla`?:optional, `max_marla`?:optional, `featured`?:optional, `status`?:optional, `limit`?:integer=20, `min_bathrooms`?:optional, `feature`?:optional, `near`?:optional, `near_km`?:number=2.0, `near_place`?:optional |

## tools

69 tools.

| Tool | Purpose | Parameters |
| --- | --- | --- |
| `tool_aerial_compare` | Compare dated aerial/satellite scenes: order, resolution and change. | `scenes`:array<object> |
| `tool_agent_commission` | Agent commission on a sale, with optional output VAT. | `price`:number, `rate`?:optional, `include_vat`?:boolean=true |
| `tool_appreciation` | Property appreciation and investment-growth projection with scenario bands. | `current_value`:number, `cagr`?:number=0.08, `years`?:integer=10, `monthly_rent`?:number=0.0, `rent_growth`?:number=0.05 |
| `tool_area_convert` | Convert between sqft / sqyd / sqm / marla / kanal / acre / hectare. | `value`:number, `from_unit`?:string="sqft", `to_unit`?:string="marla", `marla_sqft`?:number=272.25 |
| `tool_area_table` | Show an area in every supported unit at once. | `value`:number, `from_unit`?:string="sqft", `marla_sqft`?:number=272.25 |
| `tool_area_units` | Area units and marla standards supported by the converters. | — |
| `tool_brochure_pdf` | Build a branded text brochure PDF from a list of sections. | `title`:string, `subtitle`?:string="", `sections`?:optional |
| `tool_build_timeline` | Phase-weighted construction timeline (delegates to the construction wing). | `covered_area`:number, `floors`?:integer=1, `building_type`?:string="house", `system`?:string="rcc_frame" |
| `tool_cad_formats` | Supported drawing formats and what each can actually preview/convert. | — |
| `tool_cad_inspect` | Detect a drawing's format from its name/first bytes and report capabilities. | `filename`?:string="", `head_base64`?:optional, `size_bytes`?:integer=0 |
| `tool_calculators` | The calculators offered by the Tools Center, with their inputs and engines. | — |
| `tool_calendar_ics` | Render events as a downloadable iCalendar (.ics) feed. | `events`:array<object>, `calendar_name`?:string="Arz-e-Pak" |
| `tool_capital_gains_tax` | Capital-gains tax on a disposal, by holding period and filer status. | `gain`:number, `holding_years`:number, `filer`?:boolean=true |
| `tool_compare_revisions` | Compare two revisions of a plan: counts, extents and added/removed items. | `a_entities`:array<object>, `b_entities`:array<object> |
| `tool_construction_cost` | Construction-cost estimate (delegates to the construction wing's engine). | `covered_area`:number, `floors`?:integer=1, `building_type`?:string="house", `quality_tier`?:string="standard", `system`?:string="rcc_frame", `city`?:optional, `plot_area`?:optional, `escalation_years`?:number=0.0 |
| `tool_convert_guide` | Explain what a heavier conversion needs (and why), plus upload-safety notes. | `kind`:string |
| `tool_crs_catalog` | Common coordinate reference systems with guidance on which to measure in. | — |
| `tool_document_tools` | The document/conversion tools and whether each is native or needs a dependency. | — |
| `tool_dxf_preview` | Parse an ASCII DXF and render it to SVG (line/polyline/circle/text). | `text`:string, `width`?:integer=800, `height`?:integer=600 |
| `tool_export_geodata` | Export points/lines/polygons as GeoJSON or KML. | `features`:array<object>, `fmt`?:string="geojson", `name`?:string="export" |
| `tool_geo_privacy_check` | Advise on sharing precise residential coordinates (opt-in, fuzzing). | `latitude`:number, `longitude`:number |
| `tool_georeference` | Fit an image-pixel → WGS84 transform from control points (affine/similarity). | `control_points`:array<object> |
| `tool_get` | One tool card by key (e.g. ``mortgage``, ``georeference``, ``calendar``). | `key`:string |
| `tool_gregorian_from_hijri` | Convert a Hijri date to the predicted Gregorian date. | `year`:integer, `month`:integer, `day`:integer |
| `tool_hijri_from_gregorian` | Convert a Gregorian date (YYYY-MM-DD) to the predicted Hijri date. | `on`:string |
| `tool_image_resize_plan` | Compute a contain-fit resize target without touching the pixels. | `width`:integer, `height`:integer, `max_width`?:integer=1600, `max_height`?:integer=1600 |
| `tool_images_to_pdf` | Combine JPEG images into a PDF (native, no re-encoding). | `images`:array<object>, `page_size`?:string="a4" |
| `tool_import_geodata` | Parse GeoJSON or KML text into [lat, lon] coordinate lists. | `text`:string |
| `tool_installment_plan` | Developer-style installment plan: down payment, markup and monthly amount. | `price`:number, `down_payment`?:number=0.0, `months`?:integer=36, `annual_markup`?:number=0.0 |
| `tool_investment_summary` | Investment summary built on the accounting ROI engine (with scenarios). | `initial_investment`:number, `annual_cash_flow`?:number=0.0, `hold_years`?:integer=10, `terminal_value`?:number=0.0, `loan_amount`?:number=0.0, `loan_rate`?:optional |
| `tool_islamic_occasions` | The main Islamic occasions inside a Gregorian year (predicted). | `year`:integer |
| `tool_joint_investment` | Split a profit between partners pro-rata to capital, with each partner's ROI. | `partners`:array<object>, `total_profit`:number, `months`?:number=12.0 |
| `tool_length_convert` | Convert between feet, inches, yards, metres, centimetres and kilometres. | `value`:number, `from_unit`?:string="ft", `to_unit`?:string="m" |
| `tool_locate_nearby` | Locate POIs within a radius of an origin [lat, lon], nearest first. | `origin`:array<number>, `radius_m`?:number=2000.0, `category`?:optional, `limit`?:integer=20 |
| `tool_map_measure` | Distance, perimeter, area, centroid and bbox for a set of [lat, lon] points. | `coords`:array<array>, `marla_sqft`?:number=272.25 |
| `tool_material_quantities` | Approximate material take-off (delegates to the construction wing). | `covered_area`:number, `quality_tier`?:string="standard", `building_type`?:string="house" |
| `tool_milestone_calendar` | Date-stamp a construction timeline into a milestone calendar (+ .ics). | `start_date`:string, `covered_area`?:number=1000.0, `floors`?:integer=1, `building_type`?:string="house", `system`?:string="rcc_frame" |
| `tool_mortgage_calculator` | Home-loan monthly installment, total interest and full amortisation schedule. | `price`:number, `down_payment`?:number=0.0, `annual_rate`?:optional, `years`?:optional, `payments_per_year`?:integer=12 |
| `tool_pakistan_holidays` | Pakistan public holidays for a year: fixed national days + predicted Islamic ones. | `year`:integer |
| `tool_pdf_info` | Basic PDF inspection: page count and declared size. | `pdf_base64`:string |
| `tool_photo_geotag_batch` | Geotag several photos with the same coordinate. | `photos`:array<object>, `latitude`:number, `longitude`:number, `altitude`?:optional |
| `tool_photo_report` | A property photo report: markers, summary table and an embeddable map. | `photos`:array<object>, `title`?:string="Site photo report", `lang`?:string="en", `theme`?:string="auto" |
| `tool_plot_diagram` | A printable SVG diagram of a rectangular plot with its dimensions and area. | `length_ft`:number, `width_ft`:number, `label`?:string="Plot", `marla_sqft`?:number=272.25 |
| `tool_plot_dimensions` | Length / width / perimeter / diagonal of a rectangular plot from its area. | `area`:number, `from_unit`?:string="marla", `ratio`?:number=2.0, `marla_sqft`?:number=272.25 |
| `tool_plot_inventory` | Plot inventory: area in sqft / marla / kanal with price per unit. | `properties`:array<object>, `marla_sqft`?:number=272.25 |
| `tool_plot_studio` | One-shot plot brief: all-unit conversion, dimensions, diagram and optional build cost. | `value`:number, `from_unit`?:string="marla", `ratio`?:number=2.0, `covered_area`?:optional, `quality_tier`?:string="standard", `building_type`?:string="house", `marla_sqft`?:number=272.25 |
| `tool_polygon_area` | Area of a polygon from its [lat, lon] coordinates, in the requested unit. | `coords`:array<array>, `unit`?:string="sqft", `marla_sqft`?:number=272.25 |
| `tool_possession_schedule` | A booking + installment + possession payment schedule with due dates (+ .ics). | `start_date`:string, `total_price`:number, `down_payment`?:number=0.0, `months`?:integer=24, `frequency`?:string="monthly" |
| `tool_price_per_unit` | Price per sqft / sqyd / sqm / marla for a listing. | `price`:number, `area`:number, `from_unit`?:string="sqft", `marla_sqft`?:number=272.25 |
| `tool_printable_layout` | A printable plot-layout sheet (SVG) with a title block and scale bar. | `title`:string, `plot_length_ft`:number, `plot_width_ft`:number, `orientation`?:string="portrait" |
| `tool_project_delete` | Delete a saved tool project. | `project_id`:string |
| `tool_project_get` | One saved tool project by id. | `project_id`:string |
| `tool_projects` | List saved tool projects, optionally filtered by tool key. | `tool`?:optional |
| `tool_property_comparison` | Side-by-side comparison of listings with derived price/sqft and yield. | `properties`:array<object> |
| `tool_property_reminders` | Turn dated property events into reminders (possession, installments, expiries). | `events`:array<object>, `lead_days`?:integer=7 |
| `tool_read_photo_gps` | Read GPS coordinates, altitude and time from a JPEG's EXIF metadata. | `image_base64`:string |
| `tool_rent_vs_buy` | Compare buying against renting over a holding period. | `price`:number, `monthly_rent`:number, `down_payment_pct`?:number=0.2, `annual_rate`?:optional, `years`?:optional, `cagr`?:number=0.08, `rent_growth`?:number=0.05, `hold_years`?:integer=10 |
| `tool_rental_yield` | Gross and net rental yield with payback period and cap rate. | `price`:number, `monthly_rent`:number, `annual_costs`?:number=0.0, `vacancy_rate`?:number=0.0 |
| `tool_rows_to_csv` | Serialise rows of dicts to CSV text. | `rows`:array<object>, `columns`?:optional |
| `tool_rows_to_markdown` | Serialise rows of dicts to a Markdown table. | `rows`:array<object>, `columns`?:optional |
| `tool_save_project` | Save a tool run as a reusable project (personalised tools). | `name`:string, `tool`:string, `inputs`?:optional, `outputs`?:optional, `notes`?:optional |
| `tool_text_to_pdf` | Create a simple text/listings PDF (dependency-free). | `title`:string, `lines`:array<string>, `page_size`?:string="a4" |
| `tool_transfer_costs` | Stamp duty, CVT, registration, mutation and withholding on a property transfer. | `price`:number, `province`?:string="punjab", `filer`?:boolean=true, `rate_overrides`?:optional |
| `tool_transform_point` | Apply a georeference matrix (px→geo forward, or geo→px with to_geo=False). | `matrix`:object, `x`:number, `y`:number, `to_geo`?:boolean=true |
| `tool_write_photo_gps` | Embed/replace GPS coordinates in a JPEG's EXIF (returns new base64 bytes). | `image_base64`:string, `latitude`:number, `longitude`:number, `altitude`?:optional, `timestamp`?:optional |
| `tools_catalog` | The tool cards, optionally filtered by category or launch phase. | `category`?:optional, `phase`?:optional |
| `tools_categories` | The Tools Center categories and how many tools each holds. | — |
| `tools_overview` | Counts by category and phase, the native/optional split and the wing configuration. | — |
| `tools_portal` | Render the **Tools & Utilities** page (HTML): a searchable Tools Center, live | `lang`?:string="en", `theme`?:string="auto" |

## transactions

16 tools.

| Tool | Purpose | Parameters |
| --- | --- | --- |
| `transaction_close` | Close a transaction: compute commission + VAT, allocate the revenue share, post the | `tx_id`:string, `commission_rate`?:optional, `platform_share`?:number=0.2, `listing_agent_share`?:number=0.4, `selling_agent_share`?:number=0.4, `post_to_ledger`?:boolean=true, `record_payouts`?:boolean=true |
| `transaction_create` | Open a transaction with its milestone/deadline checklist (offers, KYC, title, | `transaction_type`?:string="sale", `price`?:number=0.0, `property_id`?:optional, `property_title`?:optional, `buyer_name`?:optional, `seller_name`?:optional, `listing_agent_id`?:optional, `selling_agent_id`?:optional, `commission_rate`?:optional, `start_date`?:optional, `notes`?:optional |
| `transaction_deadlines` | Every transaction milestone due within the horizon (incl. overdue), soonest first. | `horizon_days`?:integer=14 |
| `transaction_extract_terms` | Extract key contract terms, parties and dates from a sale/lease agreement text. | `text`:string |
| `transaction_get` | One transaction (id or code) with milestones, terms and offers. | `tx_id`:string |
| `transaction_milestone_add` | Add a custom milestone/deadline to a transaction. | `tx_id`:string, `key`:string, `name`:string, `due_date`?:optional, `owner`?:string="broker", `blocking`?:boolean=false |
| `transaction_milestone_complete` | Mark a transaction milestone complete. | `tx_id`:string, `key`:string, `as_of`?:optional |
| `transaction_offer_add` | Record an offer on a transaction. | `tx_id`:string, `price`:number, `buyer_name`?:optional, `terms`?:optional |
| `transaction_offer_respond` | Respond to an offer: ``counter`` (with a price), ``accept``, ``reject`` or ``withdraw``. | `offer_id`:string, `action`:string, `counter_price`?:optional |
| `transaction_progress` | Completion %, overdue milestones, next deadline and a red/amber/green status. | `tx_id`:string |
| `transaction_report` | Render a printable HTML transaction/closing report (HTML). | `tx_id`:string, `lang`?:string="en", `theme`?:string="auto" |
| `transaction_signature_add` | Record an e-signature request / signing for a transaction party. | `tx_id`:string, `signer`:string, `role`?:string="buyer", `method`?:string="esign", `signed`?:boolean=false |
| `transaction_signatures` | E-signature status: signed roles, missing roles and completeness. | `tx_id`:string |
| `transaction_stages` | The transaction lifecycle stages (draft → … → closed / fallen through). | — |
| `transaction_update` | Update a transaction's stage, price, parties or commission rate. | `tx_id`:string, `stage`?:optional, `status`?:optional, `price`?:optional, `commission_rate`?:optional, `buyer_name`?:optional, `seller_name`?:optional, `notes`?:optional |
| `transactions_list` | List transactions, optionally filtered by status, stage or type. | `status`?:optional, `stage`?:optional, `transaction_type`?:optional |

