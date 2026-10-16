# Arz-e-Pak Portal — Documentation

Documentation set for the Arz-e-Pak real-estate portal backend: a single in-house
platform that powers property discovery, GIS/mapping, CRM, accounting, construction,
maintenance, project management (PMO), team messaging and an agentic-AI layer — all
exposed **both** as an **MCP server** and a **FastAPI REST API** from one source of truth.

> **One source of truth.** Every capability is implemented once as a plain-Python
> function in `backend/` and then *exposed* twice: as an MCP tool (with matching
> resources and prompts) and as a REST endpoint. The two layers call the same function,
> so behaviour can never drift between them. Throughout this documentation, a
> "capability" therefore has one implementation and two front doors.

---

## Documentation map

| Document | Audience | What it covers |
| --- | --- | --- |
| [USER_MANUAL.md](USER_MANUAL.md) | Brokers, agents, staff, end users | Signing in, the portal pages, and step-by-step daily workflows for every wing. |
| [ADMINISTRATION_GUIDE.md](ADMINISTRATION_GUIDE.md) | Portal admins, DevOps, IT | Deployment, configuration, roles & permissions, security, data/storage & backups, monitoring, runbook. |
| [MCP_GUIDE.md](MCP_GUIDE.md) | Integration engineers, AI builders | The MCP server: transports, client setup, discovery, calling tools/resources/prompts, auth, limits. |
| [API_GUIDE.md](API_GUIDE.md) | Backend/frontend engineers | The FastAPI REST API + WebSockets + the OpenAI-compatible facade: auth, conventions, key flows, errors. |
| [AGENTIC_AI_GUIDE.md](AGENTIC_AI_GUIDE.md) | AI engineers, product owners | The Agentic OS: the 8 products, the 24-agent catalogue, the run engine, approval gates, smart actions. |
| [MESSAGING_GUIDE.md](MESSAGING_GUIDE.md) | Everyone using the messaging wing | The internal-first messaging + notification system end to end, including e-mail, Telegram and real-time. |
| [TESTING_GUIDE.md](TESTING_GUIDE.md) | Developers, QA | Running and extending the test suites; how to test MCP, the API, messaging and the agentic flows. |

### Generated reference (do not edit by hand)

These files are produced from the live code by `docs/_gen/gen_docs.py`, so they can
never fall out of sync. Regenerate them whenever the surface changes.

| Reference | Contents |
| --- | --- |
| [reference/MCP_TOOLS.md](reference/MCP_TOOLS.md) | Every MCP tool, grouped, with its purpose and parameters. |
| [reference/MCP_RESOURCES.md](reference/MCP_RESOURCES.md) | Static resources and URI resource templates. |
| [reference/MCP_PROMPTS.md](reference/MCP_PROMPTS.md) | Every MCP prompt and its arguments. |
| [reference/REST_ENDPOINTS.md](reference/REST_ENDPOINTS.md) | Every REST route, grouped by tag. |
| [reference/AGENTS.md](reference/AGENTS.md) | The agent and product catalogue with autonomy and approval flags. |
| [reference/MESSAGING.md](reference/MESSAGING.md) | Messaging catalogs: channels, categories, attachment rules, limits. |
| [reference/SETTINGS.md](reference/SETTINGS.md) | Runtime settings groups, keys and current values. |

Regenerate (from `backend/`):

```powershell
uv run python ..\docs\_gen\gen_docs.py
```

---

## The shape of the platform

```text
                     ┌──────────────────────────────┐
   MCP clients  ───▶ │  server.py  (MCP server)      │
   (Claude,          │  tools • resources • prompts  │
    Cursor,          └───────────────┬───────────────┘
    Inspector)                       │  same functions
                                     ▼
                     ┌──────────────────────────────┐
   REST clients ───▶ │  api.py  (FastAPI)            │
   (web app,        │  /…  •  /v1 (OpenAI facade)   │
    scripts)        │  /mcp (Streamable HTTP)       │
                     └───────────────┬───────────────┘
                                     │
             ┌───────────────────────┴────────────────────────┐
             ▼                                                 ▼
   framework-free domain modules (backend/*.py)      in-memory stores
   agents • transactions • intelligence • leasing    (seeded on startup,
   marketing • commercial • accounting • crm         behind a DB seam)
   gis • construction • maintenance • tools • pmo
   messaging • content • auth …
```

### Surface at a glance

| Surface | Count |
| --- | --- |
| MCP tools | **593** across **30 groups** |
| MCP resources / templates | **112** / **34** |
| MCP prompts | **31** |
| REST routes | **618** across **36 tags** |
| Portal roles / permissions | **19** / **30** |
| Agentic agents / products | **24** / **8** |

### Wing → MCP group → REST tag

| Wing | MCP tool groups | REST tag(s) |
| --- | --- | --- |
| Properties & hierarchy | `hierarchy`, `properties`* | `hierarchy`, `properties` |
| GIS, POI, AOI | `gis`, `poi`, `aoi` | `gis`, `gis-analysis`, `poi`, `aoi` |
| Accounting & finance | `accounting`, `finance` | `accounting`, `finance` |
| CRM | `crm` | `crm` |
| Construction | `construction` | `construction` |
| Maintenance | `maintenance` | `maintenance` |
| Tools & Utilities | `tools` | `tools` |
| PMO | `pmo` | `pmo` |
| Messaging | `messaging` | `messaging` |
| Agentic OS | `agents`, `intelligence`, `leasing`, `marketing`, `commercial`, `transactions`, `investment` | `agents`, `intelligence`, `leasing`, `marketing`, `commercial`, `transactions` |
| Auth & RBAC | `authentication` | `auth`, `roles` |
| Content & advertising | `content`, `advertising`, `news` | `content`, `ads`, `news` |
| Portal meta | `portal` | `portal` |

\* Some property routes carry the `properties` tag while the MCP tools are grouped under
`hierarchy`; the generated references are authoritative.

---

## Conventions used across this documentation

* **MCP tool vs REST route** — the same capability. Where a section shows a tool name
  like `msg_post`, the REST equivalent is normally `POST /messaging/...` and the
  generated [REST reference](reference/REST_ENDPOINTS.md) lists it exactly.
* **`requires_optional_dependency`** — heavy or licensed capabilities (PDF rendering,
  GeoPandas reprojection, PyMuPDF text extraction, GDAL) do **not** fake results. They
  return a structured descriptor naming the extra dependency, so a caller can degrade
  gracefully.
* **Storage seam** — data lives in in-memory stores seeded on startup, but every store
  sits behind a thin seam so it can be swapped for PostgreSQL/PostGIS + object storage.
  This is deliberate; see [ADMINISTRATION_GUIDE.md](ADMINISTRATION_GUIDE.md#5-data-storage--backups).
* **Language & theme** — every HTML page accepts `?lang=xx` (English, Urdu, …) and
  `?theme=auto|light|dark`.

## Quick start

```powershell
cd backend
uv sync                                   # install fastapi, uvicorn, httpx, mcp[cli]
uv run python main.py                     # REST :8000 · MCP /mcp · OpenAI /v1
# REST docs  -> http://127.0.0.1:8000/docs
# MCP        -> http://127.0.0.1:8000/mcp
```

Then open <http://127.0.0.1:8000/docs> for the interactive REST API, or connect an MCP
client per [MCP_GUIDE.md](MCP_GUIDE.md). New to the portal? Start with the
[User Manual](USER_MANUAL.md).
