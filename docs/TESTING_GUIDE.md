# Arz-e-Pak Portal — Testing Guide

This guide is for **developers and QA**. It explains the test layers, how to run them,
what each one covers, and how to add tests — with dedicated sections for testing the
**MCP surface**, the **REST API**, the **messaging flow** and the **AI-agentic flows**.

---

## 1. Test strategy

The portal is verified at four layers, from fastest to most realistic:

| Layer | Tool | Scope |
| --- | --- | --- |
| **1. Domain probes** | ad-hoc scripts (optional) | A single framework-free module in isolation, no MCP/FastAPI. |
| **2. Integration** | `test_integration.py` | In-process MCP client **and** FastAPI `TestClient` against the seeded app. |
| **3. Live HTTP smoke** | `smoke_http.py` | A real `uvicorn` server on port 8011 and real HTTP calls. |
| **4. Manual QA** | the running portal | Human walk-through of pages and flows (checklist below). |

The first three are automated and are what CI should run.

---

## 2. Running the suites

```powershell
cd backend

# 1. In-process integration (MCP + REST), prints every check and a summary
uv run python test_integration.py
#   ... 1005/1005 checks passed

# 2. Live HTTP smoke on :8011, prints PASS/FAIL
uv run python smoke_http.py
#   ... SMOKE: PASS
```

**Expected result:** `test_integration.py` prints `1005/1005 checks passed` and exits `0`.
`smoke_http.py` prints `SMOKE: PASS`.

> PowerShell note: piping output can make `$LASTEXITCODE`-style checks noisy. To read the
> real exit code reliably, run without a pipeline or capture it explicitly.

If port 8000 is held by a stale process, that does not affect the tests: the smoke test uses
**8011**.

---

## 3. `test_integration.py` anatomy

The suite is a single script with small helpers and per-wing check functions.

| Piece | Purpose |
| --- | --- |
| `check(name, condition, detail="")` | Record one assertion into `RESULTS`. |
| `text_of(call_result)` | Flatten an MCP tool/prompt result's text blocks to a string. |
| `_SharedClient` | A thin wrapper so async MCP checks share one client. |
| `RESULTS`, `STATE` | Global result list and a scratch dict passed between checks. |
| `main() -> int` | Runs every suite, prints the `=== Summary ===`, returns `0` only if all pass. |

Suite functions (each prints its own `===` header):

| Function | Area |
| --- | --- |
| `run_mcp_checks()` | MCP protocol, discovery, resources, prompts, core tools. |
| `run_wing_checks()` | Construction & maintenance wings (MCP). |
| `run_fastapi_checks(...)` | REST routes (properties, GIS, CRM, accounting, auth, …). |
| `run_products_checks()` | Agentic products (MCP). |
| `run_products_rest_checks(client)` | Agentic products (REST). |
| `run_tools_checks()` / `run_tools_rest_checks(client)` | Tools & Utilities (MCP/REST). |
| `run_pmo_checks()` / `run_pmo_rest_checks(client)` | PMO (MCP/REST). |
| `run_messaging_checks()` / `run_messaging_rest_checks(client)` | Messaging (MCP/REST). |

MCP checks use `async with Client(core.mcp)`, where `core` is `server.py`. REST checks use a
Starlette/FastAPI `TestClient` built from `api.app`.

---

## 4. Testing the MCP surface

MCP checks should cover the protocol and every capability, not just call a tool once.

**What to assert**

1. **Handshake & discovery** — `list_tools`, `list_resources`, `list_resource_templates`,
   `list_prompts` return the expected *minimum* counts and named entries.
2. **A tool round-trip** — call the tool and assert on the parsed result (use `text_of`).
3. **A resource read** — e.g. `portal://catalog`, `messaging://overview`.
4. **A prompt** — `get_prompt(name, arguments={...})` returns messages.
5. **Cross-check** — a tool's result agrees with the equivalent REST result.

**Recipe**

```python
from mcp import Client
import server as core

async def run_mcp_checks() -> None:
    async with Client(core.mcp) as client:
        tools = await client.list_tools()
        check("MCP exposes 593 tools", len(tools) >= 593, f"got {len(tools)}")

        result = await client.call_tool("portal_health", {})
        check("portal_health responds", "status" in text_of(result))
```

The generated [tool reference](reference/MCP_TOOLS.md) is the source of truth for names and
arguments; assert against names from there.

> Also assert that **every wing is discoverable** — e.g. at least one `msg_*`, `pmo_*`,
> `tool_*` tool — so a renamed group fails loudly.

---

## 5. Testing the REST API

REST checks use the FastAPI `TestClient`, which exercises routing, validation, status codes
and serialisation without a running server.

**What to assert**

1. **Status codes** — `200`/`201` on success, `4xx` on bad input.
2. **Body shape** — expected keys/counts, not just "truthy".
3. **Auth** — protected routes behave with and without a bearer token.
4. **HTML routes** — `GET …/portal` returns HTML; the `.html` alias always does.
5. **Cross-check** — where a route mirrors an MCP tool, compare both.

**Recipe**

```python
def run_products_rest_checks(client) -> None:
    r = client.get("/agents/overview")
    check("GET /agents/overview", r.status_code == 200 and "products" in r.json())

    r = client.post("/agents/run", json={"agent_key": "conversational_buyer_agent",
                                         "objective": "3-bed in Lahore"})
    check("POST /agents/run returns a run", r.status_code == 200 and r.json().get("run_id"))
```

The generated [endpoint reference](reference/REST_ENDPOINTS.md) lists every route.

---

## 6. Testing the messaging flow

Messaging has both an MCP suite (`run_messaging_checks`) and a REST suite
(`run_messaging_rest_checks`). A thorough messaging test walks the **whole lifecycle**, not
isolated calls.

**Recommended sequence**

1. **Workspace** — `msg_overview` / `GET /messaging/overview`; channels and counts exist.
2. **Conversations** — create a direct/group/channel and a **property thread**; assert the
   property id was validated.
3. **Membership** — add a member, update a role, remove a member.
4. **Messages** — post, reply (thread), mention, react, pin, edit (author only, inside the
   window), soft-delete; assert **mentions are re-derived on edit**.
5. **Read state** — mark read; assert unread counts drop and read receipts update.
6. **Attachments** — register a reference, mint a signed link, resolve it, and assert that
   an **expired/tampered token is rejected** and a **non-member cannot mint a link**.
7. **Actions** — create an action with an owner + deadline, and with
   `create_crm_task=true` assert a CRM task appears.
8. **Notifications** — queue, then `dispatch`; assert outbox items exist per channel and
   that preferences/quiet hours are respected (urgent exempt).
9. **Telegram** — mint a link code, simulate `/start`, assert status; assert
   `attach_allowed=false` (no documents) and that payloads are sanitised + deep-linked.
10. **WebSocket** — connect with `?user_id=`, receive a push, and assert a **denied** client
    is closed with code `4403`.
11. **Governance** — report + moderate, revoke access (user removed from all conversations),
    retention report + dry-run purge (pinned exempt).

**Recipe (MCP)**

```python
async def run_messaging_checks() -> None:
    async with Client(core.mcp) as client:
        conv = await client.call_tool("msg_create_conversation",
                                      {"kind": "group", "created_by": "USR-0001"})
        cid = json.loads(text_of(conv))["conversation"]["id"]
        post = await client.call_tool("msg_post",
                                      {"conversation_id": cid,
                                       "author_id": "USR-0001",
                                       "body": "Please verify @USR-0003"})
        check("msg_post works", "message" in text_of(post))
```

**REST equivalents:** `POST /messaging/conversations`, `POST …/messages`,
`POST …/actions`, `POST /messaging/dispatch`, `GET /messaging/outbox`,
`POST /messaging/telegram/update`, and `client.websocket_connect(...)` for the socket. See
the full recipe in the [Messaging Guide §14](MESSAGING_GUIDE.md#14-end-to-end-recipe-powershell).

---

## 7. Testing AI-agentic flows

Agentic checks (`run_products_checks`, `run_products_rest_checks`) should verify the
**safety semantics**, not just that a run returns.

**What to assert**

1. **Catalogue** — `agents_catalog` / `GET /agents/catalog` lists 24 agents and 8 products.
2. **Plan vs run** — `agent_plan` records a plan **without** side effects; `agent_run`
   executes and returns a `run_id`.
3. **Approval gate** — start a run with `approve=false` (or an `assist` agent) and assert a
   step is `awaiting_approval`; then `agent_approve` completes it. This is the single most
   important agentic test.
4. **Determinism of scoring** — `agent_move_likelihood` and `agent_seller_intent` return a
   score in `0..100` with contributing signals.
5. **Smart Actions** — `agent_smart_actions` returns prioritised items with owners/SLAs.
6. **Orchestration** — `agent_orchestrate` returns a chain no longer than
   `orchestration_max_agents`.
7. **Audit** — `agent_runs` / `GET /agents/runs` records the run and its approvals.

**Recipe**

```python
async def run_products_checks() -> None:
    async with Client(core.mcp) as client:
        run = await client.call_tool("agent_run",
                                     {"agent_key": "transaction_agent",
                                      "objective": "review a deal",
                                      "approve": False})
        rid = json.loads(text_of(run))["run"]["id"]
        got = await client.call_tool("agent_run_get", {"run_id": rid})
        check("agent paused at the gate", "awaiting_approval" in text_of(got))
        done = await client.call_tool("agent_approve", {"run_id": rid})
        check("agent_approve completes", "done" in text_of(done).lower())
```

The catalogue reference is [reference/AGENTS.md](reference/AGENTS.md); approval flags and
workflows there tell you which agents must pause.

---

## 8. Testing Tools & Utilities and PMO

* **Tools** — assert each calculator's maths (e.g. the mortgage monthly installment), the
  two **marla standards** (272.25 vs 225.0 sq-ft) and the calendar bindings.
* **PMO** — create a project, assert phases + WBS were seeded (idempotently), then check
  the **critical path**, **earned value** (`spi`/`cpi`) and **health RAG**. Remember the
  **six-day working week** and that a not-yet-started project is green with `spi`/`cpi`
  `None`.

---

## 9. Adding a new check

1. Pick the right suite function and add a `check(...)` call.
2. Prefer **cross-checks** (MCP vs REST) over duplicating expectations.
3. Assert on **structure and values**, and include a helpful `detail` for failures.
4. Run `uv run python test_integration.py` and confirm the total increases with no failures.
5. If you changed the surface, regenerate the docs reference
   ([§11](#11-keeping-the-docs-in-sync)).

```python
def run_tools_rest_checks(client) -> None:
    r = client.post("/tools/calculators/mortgage",
                    json={"price": 8000000, "down_payment": 1000000,
                          "annual_rate": 21, "years": 20})
    check("mortgage installment > 0",
          r.status_code == 200 and r.json().get("monthly_payment", 0) > 0)
```

---

## 10. Manual QA checklist

With the server running (`uv run python main.py`):

- [ ] `/docs` loads and every tag has operations.
- [ ] `/tools/portal`, `/pmo/portal`, `/messaging/portal` render; `?lang=ur&theme=dark` works.
- [ ] A GIS report opens and shows a map.
- [ ] Create a PMO project and see its earned-value view.
- [ ] Post a messaging message, then a WebSocket client receives the push.
- [ ] Turn a message into an action and see it in the CRM task list.
- [ ] Drain notifications and inspect the outbox.
- [ ] Link Telegram with a code and receive a sanitised alert.
- [ ] Open an expired attachment link and confirm it is refused.

---

## 11. Keeping the docs in sync

The reference docs are generated from the live code, so they cannot silently drift:

```powershell
cd backend
uv run python ..\docs\_gen\gen_docs.py
```

This rewrites `docs/reference/*.md` (tools, resources, prompts, REST endpoints, agents,
messaging catalogs, settings). Run it after any surface change and commit the result.

---

## 12. CI suggestion

A minimal pipeline:

```yaml
steps:
  - run: uv sync
    working-directory: backend
  - run: uv run python test_integration.py
    working-directory: backend
  - run: uv run python smoke_http.py
    working-directory: backend
```

Fail the build on a non-zero exit from either suite. Because `main()` in
`test_integration.py` returns `0` only when **every** check passed, a single regression
fails the pipeline.
