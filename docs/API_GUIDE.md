# Arz-e-Pak Portal — API Guide

This guide is for **backend and frontend engineers** consuming the portal over HTTP. It
covers base URLs, authentication, conventions, the route map, real-time WebSockets, the
OpenAI-compatible facade and error handling. For the MCP surface, see the
[MCP Guide](MCP_GUIDE.md).

---

## 1. Overview

| Item | Value |
| --- | --- |
| Framework | FastAPI (`backend/api.py`) |
| Base URL (dev) | `http://127.0.0.1:8000` |
| Interactive docs (Swagger UI) | `/docs` |
| Alternative docs (ReDoc) | `/redoc` |
| OpenAPI schema | `/openapi.json` |
| MCP (mounted) | `/mcp` |
| OpenAI facade | `/v1` |
| Routes | **630** across **37 tags** |

Every route calls a plain-Python function that the matching MCP tool also calls, so the
two surfaces are guaranteed equivalent.

### Route map (by tag)

| Tag | Routes | Wing |
| --- | --- | --- |
| `messaging` | 71 | Team Messaging |
| `tools` | 70 | Tools & Utilities |
| `pmo` | 61 | Projects & Monitoring |
| `accounting` | 32 | Accounting |
| `maintenance` | 28 | Maintenance |
| `crm` | 25 | CRM |
| `construction` | 24 | Construction |
| `gis` | 24 | GIS & mapping |
| `gis-analysis` | 18 | Spatial analysis |
| `auth` | 17 | Authentication |
| `commercial` | 17 | Commercialisation |
| `roles` | 16 | RBAC |
| `transactions` | 16 | Deal-to-close |
| `agents` | 15 | Agentic OS |
| `content` | 14 | Portal content |
| `ads` | 13 | Advertising |
| `intelligence` | 13 | Buyer/seller intelligence |
| `marketing` | 13 | Marketing |
| `leasing` | 12 | Leasing |
| `portal` | 12 | Portal meta |
| `properties` | 11 | Properties |
| `aoi` | 11 | Areas of interest |
| `poi` | 13 | Points of interest |
| `hierarchy` | 10 | Hierarchy |
| `big-projects` | 9 | Large projects |
| `finance` | 8 | Finance |
| `routing` | 8 | Routing |
| `news` | 6 | News |
| `other` / `system` / `memory` / `images` / `broker` / `property-intelligence` / `ui` / `units` / `ai` | small | Meta |

The generated [endpoint reference](reference/REST_ENDPOINTS.md) lists every path, method
and purpose grouped by tag.

---

## 2. Authentication

The API uses **bearer tokens** returned by login/signup. Send the token on protected
routes:

```
Authorization: Bearer <token>
```

### Auth flow (endpoints)

| Step | Endpoint |
| --- | --- |
| Register | `POST /auth/signup` |
| Verify OTP | `POST /auth/otp/verify` |
| Passwordless login | `POST /auth/otp/request` → `POST /auth/otp/verify` |
| Password login | `POST /auth/login` |
| Current account | `GET /auth/me` *(token required)* |
| Refresh token | `POST /auth/refresh` |
| Logout (revoke) | `POST /auth/logout` |
| Set/change password | `POST /auth/password/set` *(token required)* |
| Reset password | `POST /auth/password/reset-request` → `POST /auth/password/reset` |
| Resend OTP | `POST /auth/resend-otp` |
| Policy & counters | `GET /auth/config` |
| Audit trail | `GET /auth/events` |
| OTP outbox (dev) | `GET /auth/notifications`, `GET /auth/otps` |

### Example — password login then fetch the account

```powershell
$r = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/auth/login" `
  -ContentType "application/json" `
  -Body '{"identifier":"admin@portal.pk","password":"Admin@12345"}'
$token = $r.token
Invoke-RestMethod -Uri "http://127.0.0.1:8000/auth/me" `
  -Headers @{ Authorization = "Bearer $token" }
```

---

## 3. Conventions

* **Content type** — JSON in, JSON out (`application/json`). A few routes return HTML
  (reports, portals); those are tagged and are safe to open in a browser.
* **Language** — HTML routes accept `?lang=xx` (English, Urdu, …).
* **Theme** — HTML routes accept `?theme=auto|light|dark`.
* **Identifiers** — entities use stable ids (`PROP-0001`, `PRJ-0001`, `CNV-0001`, …) and
  many lookups accept a code as well as an id.
* **HTML aliases** — pages like `/pmo/portal` also have `/pmo/portal.html`, which always
  serves HTML regardless of content negotiation.
* **Persistence** — data is seeded in memory (see
  [Administration §5](ADMINISTRATION_GUIDE.md#5-data-storage--backups)); the API shape is
  the same once the DB seam is enabled.

---

## 4. Key flows

### 4.1 Properties

```powershell
# list / search
curl "http://127.0.0.1:8000/properties?city=lahore"
# one property
curl "http://127.0.0.1:8000/properties/PROP-0001"
# compare two
curl "http://127.0.0.1:8000/properties/PROP-0001/compare/PROP-0002"
# correct coordinates
curl -X PUT "http://127.0.0.1:8000/properties/PROP-0001/coordinates" `
  -H "Content-Type: application/json" -d '{"latitude":31.52,"longitude":74.35}'
# houses within 1 km of a school / mosque / mall / hospital / park ... (closest first)
curl "http://127.0.0.1:8000/search?category=house&near=school&near_km=1"
# listings with a feature (matches amenities and description)
curl "http://127.0.0.1:8000/search?feature=solar&min_bathrooms=4"
# nearest school, mosque, hospital, mall, park, transport ... around one listing
curl "http://127.0.0.1:8000/properties/PROP-0001/nearby?radius_km=3"
```

`near` takes `school`, `mosque` (or `masjid`), `hospital`, `mall`, `market`, `park`, `bank`,
`restaurant`, `transport` or `fuel`, or a POI category. Nearby places come from the portal's
POI data (`/poi`); add POIs for areas that have none. Listings carry an `amenities` list that
`/me/listings` and `PUT /properties/{id}` accept.

#### My listings (signed-in account)

Listings created through `/me/listings` are owned by the caller (`owner_user_id`); agents
are attributed automatically. The portable app (`portable/`) uses these routes.

```powershell
$H = @{ Authorization = "Bearer $token" }
# publish
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/me/listings" -Headers $H `
  -ContentType "application/json" `
  -Body '{"title":"10 Marla House","price":45000000,"city_id":"<city id>","marla_area":10}'
# mine / edit / delete
Invoke-RestMethod -Uri "http://127.0.0.1:8000/me/listings" -Headers $H
Invoke-RestMethod -Method Put -Uri "http://127.0.0.1:8000/me/listings/<id>" -Headers $H `
  -ContentType "application/json" -Body '{"status":"sold"}'
# attach a photo (JPEG/PNG/WebP, base64, max 5 MB) -> served from /media/uploads/<file>
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/me/listings/<id>/photos" -Headers $H `
  -ContentType "application/json" -Body '{"data_url":"data:image/jpeg;base64,...","is_primary":true}'
```

Only the owner (or an admin) can edit, delete or add photos to a listing (`403` otherwise).

### 4.2 GIS

```powershell
# a printable analysis report (HTML)
start "http://127.0.0.1:8000/gis/report/property/PROP-0001"
# nearby amenities
curl "http://127.0.0.1:8000/gis/nearby/31.52/74.35/2.0"
# export geometry
curl "http://127.0.0.1:8000/gis/geojson/property/PROP-0001"
```

### 4.3 Tools & Utilities

```powershell
# mortgage amortisation (Tools Center card)
curl -X POST "http://127.0.0.1:8000/tools/calculators/mortgage" `
  -H "Content-Type: application/json" `
  -d '{"price":8000000,"down_payment":1000000,"annual_rate":21,"years":20}'
# finance view of the same
curl "http://127.0.0.1:8000/finance/mortgage?principal=8000000&rate=21&years=20"
```

### 4.4 CRM

```powershell
curl "http://127.0.0.1:8000/crm/leads"
curl "http://127.0.0.1:8000/crm/pipeline"
curl "http://127.0.0.1:8000/broker/contacts"   # intent-scored contacts
```

### 4.5 PMO

```powershell
# create a project (seeds phases + WBS from its type template)
curl -X POST "http://127.0.0.1:8000/pmo/projects" `
  -H "Content-Type: application/json" `
  -d '{"name":"Gulberg Heights","project_type":"residential","city":"Lahore"}'
# earned value
curl "http://127.0.0.1:8000/pmo/projects/PRJ-0001/earned-value"
# critical path
curl "http://127.0.0.1:8000/pmo/projects/PRJ-0001/critical-path"
```

### 4.6 Messaging

```powershell
# a user's conversations
curl "http://127.0.0.1:8000/messaging/conversations?user_id=USR-0001"
# post a message
curl -X POST "http://127.0.0.1:8000/messaging/conversations/CNV-0001/messages" `
  -H "Content-Type: application/json" `
  -d '{"author_id":"USR-0001","body":"Please verify the title for plot 12."}'
# turn it into an action
curl -X POST "http://127.0.0.1:8000/messaging/conversations/CNV-0001/actions" `
  -H "Content-Type: application/json" `
  -d '{"created_by":"USR-0001","title":"Verify title for plot 12","kind":"verification","message_id":"MSG-0001","owner_id":"USR-0004","create_crm_task":true}'
# drain the notification queue
curl -X POST "http://127.0.0.1:8000/messaging/dispatch"
```

Full end-to-end coverage is in the [Messaging Guide](MESSAGING_GUIDE.md).

### 4.7 Agentic OS

```powershell
curl "http://127.0.0.1:8000/agents/catalog"
curl "http://127.0.0.1:8000/agents/smart-actions?user_id=USR-0001"
curl -X POST "http://127.0.0.1:8000/agents/run" `
  -H "Content-Type: application/json" `
  -d '{"agent_key":"conversational_buyer_agent","objective":"3-bed in DHA under 3 crore","approve":true}'
# a run that paused at the human gate:
curl -X POST "http://127.0.0.1:8000/agents/runs/ARUN-0001/approve"
```

See the [Agentic AI Guide](AGENTIC_AI_GUIDE.md) for autonomy and approval semantics.

---

## 5. Real-time: WebSocket

The messaging wing exposes a per-conversation WebSocket:

```
WS /ws/messaging/{conversation_id}?user_id=<user_id>
```

* Access is **re-checked** on connect; a denied client is closed with code **`4403`**.
* `user_id` is required (there is no ambient HTTP session).
* Events pushed include new messages, edits, reactions, read receipts and action changes.
* The server uses a stdlib pub/sub broker; clients should reconnect with backoff on drop.
* Delivery semantics and reconnect handling are described in the
  [Messaging Guide](MESSAGING_GUIDE.md#10-real-time-websockets).

Example (browser):

```js
const ws = new WebSocket("ws://127.0.0.1:8000/ws/messaging/CNV-0001?user_id=USR-0001");
ws.onmessage = (e) => console.log("event", JSON.parse(e.data));
ws.onclose = (e) => { if (e.code === 4403) console.warn("access denied"); };
```

---

## 6. OpenAI-compatible facade

Mounted at `/v1` (see `backend/openai_facade.py`). Use it when a client probes for an
OpenAI-style API.

| Endpoint | Purpose |
| --- | --- |
| `GET /v1/models` | List models (local catalogue, or upstream when proxying). |
| `GET /v1/models/{model_id}` | One model. |
| `POST /v1/chat/completions` | Chat completion. |
| `POST /v1/completions` | Legacy completion. |
| `POST /v1/embeddings` | Deterministic hash embedding (local) or upstream. |

**Two modes:**

* **Local fallback (default)** — answers from the portal's own catalogue via RAG, so it
  works with no external service; embeddings are a deterministic hash.
* **Proxy mode** — set `PORTAL_LLM_BASE_URL`, `PORTAL_LLM_API_KEY` and
  `PORTAL_LLM_MODEL` to forward to a real OpenAI-compatible LLM (OpenAI, Ollama,
  LM Studio, vLLM, …). Streaming is passed through.

### Assistant helpers (OpenAI)

| Endpoint | Purpose |
| --- | --- |
| `GET /ai/capabilities` | The chat model (`local` fallback or `upstream` OpenAI) and OpenAI voice status: `voice.{provider, stt, tts, realtime, realtime_model, voice}`. No secrets. |
| `POST /ai/realtime/session` | `{"reply_lang": "auto" \| "ur" \| "en"}` returns `{"client_secret", "expires_at", "model", "calls_url", "voice"}`. The app posts its WebRTC SDP offer to `calls_url` with `Authorization: Bearer <client_secret>` (`Content-Type: application/sdp`). Send the user's bearer token to personalise the agent. Returns `501` without `OPENAI_API_KEY`. |
| `GET /ai/tools` | The assistant's tools in Chat Completions format: `search_listings`, `get_listing`, `request_call`, `my_listings`, `draft_listing`. These are the same tools the live agent gets. The app runs the calls itself, so typed chat and voice notes can search and act. |
| `POST /ai/transcribe` | `{"audio_base64", "mime_type"}` returns `{"text"}`, transcribed by OpenAI `gpt-transcribe` with Urdu and English expected. |
| `POST /ai/speak` | `{"text", "language"}` returns `{"audio_base64", "mime_type": "audio/mpeg"}` from OpenAI text-to-speech. |

**Chat:** with `OPENAI_API_KEY` set, `/v1/chat/completions` forwards to OpenAI (model
`gpt-5.6-luna`, or `OPENAI_MODEL`). A request that names the local model id is sent to
that model instead.

### CORS

The API sends CORS headers so the portable desktop app and separately hosted front ends
can call it. Auth is a bearer header (no cookies), so the default is `*`; set
`PORTAL_CORS_ORIGINS` to a comma-separated allow-list to restrict it.

---

## 7. Rate limits, errors & status codes

| Code | Meaning |
| --- | --- |
| `200` | Success. |
| `400` | Malformed request / invalid parameters. |
| `401` | Missing or invalid bearer token, bad credentials. |
| `403` | Authenticated but not permitted (e.g. unverified account, restricted channel). |
| `404` | Unknown entity id. |
| `409` | Conflict (e.g. duplicate, cooldown). |
| `429` | Rate limited (OTP resend/per-hour caps; messaging per-minute limits). |
| `4403` | WebSocket close code — access denied to the conversation. |

Auth rate limits come from the `auth` settings group (resend cooldown, hourly caps).
Messaging rate limits come from the `messaging` group
(`rate_limit_per_minute`, `rate_limit_burst`).

Capabilities that require a heavy/licensed library return a structured
`requires_optional_dependency` payload instead of a fake result — see
[Administration §9](ADMINISTRATION_GUIDE.md#9-optional-dependencies).

---

## 8. Testing the API

The in-process integration suite and the live HTTP smoke test both exercise the REST
surface:

```powershell
cd backend
uv run python test_integration.py   # FastAPI TestClient assertions
uv run python smoke_http.py         # real HTTP against :8011
```

The [Testing Guide](TESTING_GUIDE.md) explains coverage, expected output and how to add
new API checks.
