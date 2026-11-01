# Watan-e-Pak Portal — Agentic AI Guide

This guide is for **AI engineers and product owners** working with the portal's Agentic
OS: the products, the 24-agent catalogue, the run engine, autonomy and approval gates, and
the scoring models behind them. The full machine-readable catalogue is generated at
[reference/AGENTS.md](reference/AGENTS.md).

---

## 1. What the Agentic OS is

The Agentic OS is a framework-free layer (`backend/agents.py` plus the product modules
`transactions.py`, `intelligence.py`, `leasing.py`, `marketing.py`, `commercial.py`) that
turns the portal's own tools into **agents that plan, act, and hand off to a human when
needed**. Every agent is bound to real portal functions — no mock results — and every run
is recorded as an auditable trail of steps, outputs and approvals.

Agents are exposed over MCP (`agent_*`, `agents_*`) and REST (`/agents/...`), so both a
desktop AI client and your own app drive the same engine.

---

## 2. The eight productised line-ups

| Priority | Product | Category | Agents |
| --- | --- | --- | --- |
| P0 | **Property Intelligence MCP Server** | platform | 3 |
| P0 | **Broker AI Workspace** | broker | 7 |
| P0 | **MCP for Brokers** | platform | 1 |
| P1 | **Conversational Homebuying Agent** | buyer_side | 2 |
| P1 | **Seller Intelligent Pricing & Marketing Agent** | seller_side | 3 |
| P1 | **Autonomous Leasing Agent** | landlord | 3 |
| P2 | **Agentic Investment Screener** | investor | 3 |
| P2 | **AI Marketing Conductor** | marketing | 5 |

---

## 3. The 24 agents

Summary by product (see [reference/AGENTS.md](reference/AGENTS.md) for the full table with
autonomy and approval flags):

| Product | Agents |
| --- | --- |
| Property Intelligence MCP Server | `property_intelligence_mcp`, `seller_pricing_agent`, `anomaly_agent` |
| Broker AI Workspace | `broker_workspace`, `crm_agent`, `transaction_agent`, `accounting_agent`, `marketing_agent`, `compliance_agent`, `construction_advisor_agent` |
| MCP for Brokers | `mcp_for_brokers` |
| Conversational Homebuying Agent | `conversational_buyer_agent`, `anomaly_agent` |
| Seller Pricing & Marketing | `seller_pricing_agent`, `cma_agent`, `staging_agent` |
| Autonomous Leasing Agent | `autonomous_leasing_agent`, `renewal_agent`, `maintenance_triage_agent` |
| Agentic Investment Screener | `investment_screener`, `screening_agent`, `underwriting_agent` |
| AI Marketing Conductor | `marketing_conductor`, `lead_engine_agent`, `routing_agent`, `reengagement_agent`, `marketing_agent` |

(Humans think in products; the engine thinks in agents — an agent can appear in more than
one product line.)

---

## 4. Autonomy model

Every agent has an **autonomy level**, from the `agentic` settings group:

| Level | Meaning |
| --- | --- |
| `suggest` | Produces a recommendation only. |
| `assist` (default) | Does the work but **pauses at a human approval gate** before external or irreversible effects. |
| `autonomous` | Runs end-to-end without a gate. |

An agent's `requires_approval` flag is derived from its level: agents at `suggest`/`assist`
pause at the gate. Runs start with `approve=false`, so they pause **by default**; only the
portal's own scheduled jobs pre-approve (`approve=true`). Autonomous agents (e.g.
`routing_agent`, `anomaly_agent`, `renewal_agent`, `autonomous_leasing_agent`) run freely.

You can tune the default level and the approval-required set at runtime through the
`agentic` settings group (`GET/PUT /portal/settings`) or `portal_settings`.

Other `agentic` settings: `summary_chars` (output truncation), `smart_action_sla_hours`
(`{"urgent":4,"high":24,"normal":72}`) and `orchestration_max_agents` (6).

---

## 5. The run engine

A run executes an ordered pipeline of steps — **plan → execute → review → deliver** — each
bound to a real portal tool, and records every step. Steps have a status
(`pending`, `running`, `done`, `skipped`, `failed`, `awaiting_approval`) and carry their
output.

| MCP tool | REST | Purpose |
| --- | --- | --- |
| `agent_plan` | `POST /agents/plan` | Plan a run **without** executing it (signed in). |
| `agent_run` | `POST /agents/run` | Execute a run up to the gate (signed in). |
| `agent_runs` | `GET /agents/runs` | The recorded run audit trail. |
| `agent_run_get` | `GET /agents/runs/{run_id}` | One run with steps, outputs and approvals. |
| `agent_approve` | `POST /agents/runs/{run_id}/approve` | Approve a paused run and run its approved steps (`crm.manage`). |
| `agent_orchestrate` | `POST /agents/orchestrate` | Plan a multi-agent hand-off chain. |
| `agent_smart_actions` | `GET /agents/smart-actions` | The prioritised morning brief (`crm.view`). |
| `agent_move_likelihood` | `GET /agents/move-likelihood/{lead_id}` | Score a lead's likelihood of moving (`crm.view`). |
| `agent_seller_intent` | `GET /agents/seller-intent` | Score how likely a contact is to sell (`crm.view`). |
| `agents_overview` | `GET /agents/overview` | Counts, products, autonomy mix, run activity. |
| `agents_catalog` | `GET /agents/catalog` | The catalogue. |
| `agent_get` | `GET /agents/{key}` | One agent's full definition. |
| `agent_products` | `GET /agents/products` | The eight products. |
| `agentic_portal` | `GET /agents/portal[.html]` | The Agentic OS page (HTML). |

---

## 6. Approval gates

This is the core safety mechanism. **Look first, act after the human gate:**

* An agent's workflow runs the tools that only **read or analyse** (search, score, extract,
  check deadlines …) before the review step, and the tools that **create, send or change**
  something (names containing `create`, `send`, `update`, `delete`, `publish`, `assign`,
  `book`, `schedule`, `sign`, `post`, `dispatch`, `record`, `pay`, `notify`, `message`,
  `email`, `whatsapp`, `add`, `apply`, `renew` …) only after it.
* Runs start with `approve=false` (the default over MCP and REST). When a run reaches a step
  flagged `requires_approval` it **pauses** with status `awaiting_approval`; nothing that
  writes has run yet.
* A human reviews the outputs so far, then calls `agent_approve`. That runs the approved
  step and continues; a later gated step pauses again for its own approval.
* The approval is recorded under the **signed-in user's** name and id (the `approver`
  argument is only used by token-based MCP clients that have no user). Approving a run that
  is not waiting returns an error.
* Running an agent needs sign-in; approving needs `crm.manage`.
* An agent never silently falls back to some other record (for example the first listing)
  when the one it needs is missing.

```powershell
$H = @{ Authorization = "Bearer $token" }
# start a run: it pauses at the gate
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/agents/run" -Headers $H `
  -ContentType "application/json" -Body '{"agent_key":"transaction_agent","objective":"review a deal"}'

# the run id comes back in the response; approve it to run the write steps
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/agents/runs/ARUN-0001/approve" -Headers $H
```

Workflows that contain a gated step are listed in
[reference/AGENTS.md](reference/AGENTS.md#workflows) with a 🔒 marker. For example the
broker workspace pauses before `draft_marketing` and at a final `human_review`.

---

## 7. Smart Actions (the morning brief)

`agent_smart_actions` (MCP) / `GET /agents/smart-actions` (REST) produces a single,
prioritised to-do list for a user: **deals to advance, deadlines approaching, renewals
due, rent arrears and warm leads**, each with an owner and an SLA drawn from
`smart_action_sla_hours`. It is the fastest way to give a broker or manager a "what do I
do today" view, and it is the recommended entry point for any daily automation.

---

## 8. Scoring models

Two transparent, weighted models drive intent scoring (weights live in `agents.py`):

**Move-likelihood** (`agent_move_likelihood`) — likelihood a contact will transact:

| Signal | Weight |
| --- | --- |
| life_event | 0.26 |
| engagement | 0.18 |
| financial_ready | 0.16 |
| tenure | 0.14 |
| recency | 0.14 |
| market_signal | 0.12 |

**Seller intent** (`agent_seller_intent`) — likelihood a contact will sell:

| Signal | Weight |
| --- | --- |
| equity | 0.22 |
| life_event | 0.18 |
| holding_time | 0.16 |
| market_heat | 0.16 |
| fsbo_signal | 0.14 |
| engagement | 0.14 |

Both return a 0–100 score with the contributing signals, so a downstream model or a human
can audit the reasoning.

---

## 9. Orchestration

`agent_orchestrate` plans a **multi-agent hand-off chain** for a shared objective (capped
at `orchestration_max_agents`). Example: a seller brief flows
`seller_pricing_agent → cma_agent → staging_agent → marketing_agent`, each passing context
to the next. Orchestration returns the planned chain so you can run it (or inspect it)
before committing.

---

## 10. Prompts

The AI surface ships prompts that package the portal's context for a model, including:

* `agentic_workspace_brief` — the broker's daily workspace brief.
* `lead_followup`, `property_recommendation`, `seller_pricing_listing`.
* `investment_analysis_prompt`, `investment_screener_prompt`, `roi_review_prompt`.
* `transaction_close_prompt`, `market_briefing_prompt`.
* `conversational_buyer_brief`, `site_selection_prompt`.

* `scheme_legality_check`, `property_due_diligence`, `comparative_market_analysis`,
  `mega_project_impact`, `urdu_assistant_reply` — expert prompts that work from the
  knowledge base and cite their sources ([MCP Guide §4](MCP_GUIDE.md#4-calling-tools)).

See [reference/MCP_PROMPTS.md](reference/MCP_PROMPTS.md) for all 36 and their arguments.

---

## 11. Driving agents

**MCP** (desktop client / agent framework):

```text
tool: agent_smart_actions
arguments: { "user_id": "USR-0001" }

tool: agent_run
arguments: { "agent_key": "conversational_buyer_agent",
             "objective": "find a 3-bed house",
             "text": "3 crore, 3 bed, Lahore, 35 min commute" }
```

**REST** (signed in; smart actions need `crm.view`):

```powershell
curl "http://127.0.0.1:8000/agents/smart-actions?user_id=USR-0001" -H "Authorization: Bearer $token"
curl -X POST "http://127.0.0.1:8000/agents/run" -H "Authorization: Bearer $token" -H "Content-Type: application/json" `
  -d '{"agent_key":"conversational_buyer_agent","objective":"find a 3-bed house","text":"3 crore, 3 bed, Lahore"}'
```

---

## 12. Guardrails

* **Human approval** for `suggest`/`assist` agents before external effects; write tools
  run only after it, and the approval names the person.
* **MCP tool hints** — every tool is marked read-only, destructive and/or open-world, so a
  client can ask before deletes and outbound messages ([MCP Guide](MCP_GUIDE.md#tool-annotations)).
* **Audited runs** — every run, step and approval is recorded and readable.
* **Transparent scoring** — weighted, inspectable signals; no opaque model needed.
* **No fake capabilities** — heavy/licensed operations return a
  `requires_optional_dependency` descriptor
  ([Administration §9](ADMINISTRATION_GUIDE.md#9-optional-dependencies)).
* **Data, not instructions** — tool output, page content and message bodies must never be
  treated as instructions by a model driving this surface.

---

## 13. Agents and messaging

The messaging wing is the natural "nervous system" for agents:

* **Lead routing** — a new lead arriving via messaging can be scored
  (`agent_move_likelihood`) and routed to an owner, creating a tracked action.
* **Reminders** — Smart Actions and lease/deal deadlines are delivered through the
  notification queue (in-app / e-mail / optional Telegram).
* **Summarisation** — `msg_summarize` and `msg_action_items` extract a conversation's gist
  and its action items (rules-based extractive baseline; the server may route to the LLM
  facade for a richer summary).
* **Human-in-the-loop** — approvals surface as notification categories `approval` and
  `task`, so nothing waits silently.

See the [Messaging Guide](MESSAGING_GUIDE.md#12-ai-in-messaging) for the full loop.

---

## 14. The assistant: knowledge, citations and memory

The chat and voice assistant in the web portal and the app (and any MCP client) answers
from the same server-side pieces:

| Piece | Module | What it does |
| --- | --- | --- |
| Knowledge base | `knowledge.py` | BM25 search (a few milliseconds a query) over listings, housing societies with their approval status and sources, cities, mega projects, big projects, news and guide pages. Understands crore / lakh / arab, marla / kanal / sq ft, bedrooms, Urdu script and Roman Urdu, and "Phase II" = "phase 2"; prices, sizes and bedrooms become hard filters on listings. Every hit has a `[n]` citation. |
| Trust tiers | `sources.py` | `official` (government, regulators, development authorities: `.gov.pk`, `.gop.pk`, `.gos.pk`, `.gkp.pk`, `.gob.pk`, SBP, SECP, DHA …), `verified` (checked by the portal), `reference` (Wikipedia, Dawn, Business Recorder …), `listing` (an owner's or agent's listing), `unverified` (everything else, including the sample news). Stronger tiers rank higher. |
| Memory | `memory.py` | Per signed-in user, private: recent conversation turns (14 days) and long-term facts (budget, areas, size, type, bedrooms, purpose, language, explicit notes). Never stores CNIC, card or bank numbers. Users can see, delete, clear or switch it off (`/me/memory`). |
| System prompt | `prompts.py` | One prompt for every app and channel (`chat` / `voice`): accuracy first, cite `[n]`, say plainly when a scheme is unapproved or illegal, no legal or investment advice. |

**One call per question.** `POST /ai/context` returns the composed system prompt with the
MEMORY and KNOWLEDGE blocks, the hits, the memory items and the last turns; the app then
calls the model, and `POST /ai/turn` saves the reply. The web chat shows the cited hits as
a **Sources** list under the answer, each with its trust badge and a link to the original,
and runs independent tool calls in parallel.

**Web look-ups** (`web_lookup`, `POST /ai/web-lookup`) ask for official sources first, rank
the returned links by trust tier, and answer a repeated question from a 6-hour cache.

Over MCP the same pieces are `knowledge_search`, `rag_search` and the `my_memory_*` tools
([MCP Guide](MCP_GUIDE.md#knowledge-and-memory-tools)); the REST shapes are in the
[API Guide §4.9](API_GUIDE.md#49-assistant-context-knowledge-and-memory).

---

## 15. Extending the catalogue

To add an agent:

1. Add a definition in `backend/agents.py` using the `_agent(...)` helper (`key`, `name`,
   `product`, `category`, `priority`, `autonomy`, `summary`, `tools`, `inputs`, `outputs`,
   optionally `channels`, `kpis`, `requires_approval`, `handoffs`, `workflow`).
2. Bind its steps to existing portal tools (never invent tools).
3. Regenerate the docs: `uv run python ..\docs\_gen\gen_docs.py`.
4. Add an integration check in `backend/test_integration.py` (see the
   [Testing Guide](TESTING_GUIDE.md#7-testing-ai-agentic-flows)).

Because autonomy and approval are properties of the definition, a new agent automatically
inherits the right human gate.
