# Agentic catalogue

**24 agents** grouped into **8 productised line-ups**. Autonomy levels: `suggest`, `assist`, `autonomous`. Any agent whose autonomy is in ['suggest', 'assist'] pauses at a human approval gate unless the caller overrides it.

## Products

| Key | Name | Priority | Category | Agents |
| --- | --- | --- | --- | --- |
| `property_intelligence_mcp` | Property Intelligence MCP Server | P0 | platform | 3 |
| `broker_ai_workspace` | Broker AI Workspace | P0 | broker | 7 |
| `mcp_for_brokers` | MCP for Brokers | P0 | platform | 1 |
| `conversational_homebuying_agent` | Conversational Homebuying Agent | P1 | buyer_side | 2 |
| `seller_pricing_marketing_agent` | Seller Intelligent Pricing & Marketing Agent | P1 | seller_side | 3 |
| `autonomous_leasing_agent` | Autonomous Leasing Agent | P1 | landlord | 3 |
| `agentic_investment_screener` | Agentic Investment Screener | P2 | investor | 3 |
| `ai_marketing_conductor` | AI Marketing Conductor | P2 | marketing | 5 |

## Agents

| Key | Name | Product | Priority | Autonomy | Approval gate | Summary |
| --- | --- | --- | --- | --- | --- | --- |
| `property_intelligence_mcp` | Property Intelligence MCP Server | `property_intelligence_mcp` | P0 | autonomous | no | Exposes the portal's data as pay-per-call MCP tools for external AI clients. |
| `mcp_for_brokers` | MCP for Brokers | `mcp_for_brokers` | P0 | autonomous | no | Lets brokers run CRM, accounting and GIS from Claude / ChatGPT / Cursor. |
| `broker_workspace` | Broker AI Workspace | `broker_ai_workspace` | P0 | assist | yes | An Agentic OS for brokers: CRM, transaction, accounting and marketing agents. |
| `crm_agent` | CRM Agent | `broker_ai_workspace` | P0 | assist | yes | Watches contact lifecycle events, scores move-likelihood and drafts outreach. |
| `transaction_agent` | Transaction Agent | `broker_ai_workspace` | P0 | assist | yes | Extracts contract terms, creates transactions, tracks every deadline and signatures. |
| `accounting_agent` | Accounting Agent | `broker_ai_workspace` | P0 | assist | no | Tracks commissions, posts to the ledger and keeps statements current on close. |
| `marketing_agent` | Marketing Agent | `broker_ai_workspace` | P0 | assist | yes | Generates social posts, reels and market reports from listing photos; human approves. |
| `conversational_buyer_agent` | Conversational Homebuying Agent | `conversational_homebuying_agent` | P1 | assist | yes | Understands a buyer's brief in natural language, then recommends and progresses. |
| `anomaly_agent` | Bargain / Anomaly Agent | `conversational_homebuying_agent` | P1 | autonomous | no | Z-score scans the market for positive price deviations below the area average. |
| `seller_pricing_agent` | Seller Intelligent Pricing & Marketing Agent | `seller_pricing_marketing_agent` | P1 | assist | yes | Turns an address into a pricing range, confidence level and marketing kit. |
| `cma_agent` | CMA Agent | `seller_pricing_marketing_agent` | P1 | assist | yes | Adjusts comparable sales and produces a defensible pricing range in seconds. |
| `staging_agent` | Virtual Staging Agent | `seller_pricing_marketing_agent` | P1 | assist | yes | Suggests virtual staging and generates drone-style video scripts from photos. |
| `autonomous_leasing_agent` | Autonomous Leasing Agent | `autonomous_leasing_agent` | P1 | autonomous | no | Answers rental inquiries 24/7 across channels, screens applicants and renews. |
| `renewal_agent` | Renewal Agent | `autonomous_leasing_agent` | P1 | autonomous | no | Recommends renewal rents and retention actions before leases expire. |
| `maintenance_triage_agent` | Maintenance Triage Agent | `autonomous_leasing_agent` | P1 | autonomous | no | Classifies tenant repair reports and routes them to the maintenance wing. |
| `investment_screener` | Agentic Investment Screener | `agentic_investment_screener` | P2 | assist | yes | Screens properties into the top risk-adjusted returns and watches the exit window. |
| `screening_agent` | Screening Agent | `agentic_investment_screener` | P2 | assist | yes | Filters a candidate pool to the top risk-adjusted opportunities. |
| `underwriting_agent` | Underwriting Agent | `agentic_investment_screener` | P2 | assist | yes | Computes after-tax cash flow, IRR, DSCR and valuation for a deal. |
| `marketing_conductor` | AI Marketing Conductor | `ai_marketing_conductor` | P2 | assist | yes | Coordinates lead generation, routing, qualification and re-engagement. |
| `lead_engine_agent` | Lead Engine Agent | `ai_marketing_conductor` | P2 | assist | yes | Holds cross-channel 24/7 conversations and qualifies inbound leads. |
| `routing_agent` | Routing Agent | `ai_marketing_conductor` | P2 | autonomous | no | Routes leads by postcode, language, price range and source. |
| `reengagement_agent` | Re-engagement Agent | `ai_marketing_conductor` | P2 | autonomous | no | Mines dormant leads, flags false negatives and reactivates them. |
| `construction_advisor_agent` | Construction Advisor Agent | `broker_ai_workspace` | P1 | assist | yes | Bridges the construction wing: technique, cost, timeline and impact advice. |
| `compliance_agent` | Compliance Agent | `broker_ai_workspace` | P0 | assist | yes | Checks listings, KYC/AML and transaction documents against RERA and policy. |

## Workflows

Agents with a scripted workflow list the ordered steps below; a step with `approval` pauses the run at the human gate.

| Agent | Steps |
| --- | --- |
| `broker_workspace` | morning_brief (`smart_actions`) → score_contacts (`move_likelihood`) → extract_contracts (`transaction_terms_extract`) → check_deadlines (`transaction_deadlines`) → commission_projection (`commission_projection`) → draft_marketing (`marketing_generate_content`) 🔒 → human_review 🔒 → deliver |
| `conversational_buyer_agent` | parse_requirement (`buyer_parse_requirement`) → recommend (`buyer_recommend`) → find_bargains (`buyer_anomaly_scan`) → affordability (`buyer_affordability`) → human_review 🔒 → deliver |
| `seller_pricing_agent` | pull_comps (`seller_cma`) → net_proceeds (`seller_net_proceeds`) → marketing_kit (`seller_marketing_assets`) 🔒 → human_review 🔒 → deliver |
| `autonomous_leasing_agent` | answer_inquiry (`leasing_inquiry`) → check_rent_floor (`rent_floor`) → screen_application (`leasing_screen_application`) → renewals (`leasing_renewals`) → deliver |
| `investment_screener` | screen (`investment_screen`) → underwrite (`investment_underwrite`) → portfolio_alerts (`investment_portfolio_alerts`) → human_review 🔒 → deliver |
| `marketing_conductor` | qualify (`marketing_qualify_lead`) → route (`marketing_route_lead`) → reengage (`marketing_reengagement`) → content (`marketing_generate_content`) 🔒 → human_review 🔒 → deliver |

