# Watan-e-Pak Portal — API Guide

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
| Routes | **700** across **40 tags** |

Every route calls a plain-Python function that the matching MCP tool also calls, so the
two surfaces are guaranteed equivalent.

### Route map (by tag)

| Tag | Routes | Wing |
| --- | --- | --- |
| `messaging` | 71 | Team Messaging |
| `tools` | 70 | Tools & Utilities |
| `pmo` | 61 | Projects & Monitoring |
| `crm` | 35 | CRM |
| `accounting` | 32 | Accounting |
| `maintenance` | 28 | Maintenance |
| `gis` | 26 | GIS & mapping (incl. layer upload / publish) |
| `construction` | 24 | Construction |
| `gis-analysis` | 18 | Spatial analysis |
| `properties` | 18 | Properties, my listings |
| `places` | 17 | Places, areas, map overlays (`/geo/*`), mega projects |
| `auth` | 17 | Authentication |
| `commercial` | 17 | Commercialisation |
| `ads` | 16 | Advertising |
| `roles` | 16 | RBAC |
| `transactions` | 16 | Deal-to-close |
| `admin` | 15 | Base data, property database |
| `agents` | 15 | Agentic OS |
| `content` | 14 | Portal content |
| `portal` | 14 | Portal meta, settings, storage |
| `intelligence` | 13 | Buyer/seller intelligence |
| `marketing` | 13 | Marketing |
| `poi` | 13 | Points of interest |
| `aoi` | 12 | Areas of interest |
| `leasing` | 12 | Leasing |
| `ai` | 11 | Assistant: context, knowledge, voice, web look-up, `/rag` |
| `hierarchy` | 11 | Hierarchy |
| `big-projects` | 9 | Large projects |
| `routing` | 9 | Routing |
| `masterplans` | 9 | DHA master plans |
| `finance` | 8 | Finance |
| `news` | 6 | News |
| `me` | 5 | Assistant memory |
| `system` / `broker` / `images` / `memory` / `property-intelligence` / `ui` / `units` | small | Meta |

The generated [endpoint reference](reference/REST_ENDPOINTS.md) lists every path, method
and purpose grouped by tag.

---

## 2. Authentication

The API uses **bearer tokens** returned by login/signup. Send the token on protected
routes:

```
Authorization: Bearer <token>
```

### What needs a token

One access guard checks every request before the route runs (deny by default):

* **Reads** (`GET`) are public unless a rule says otherwise — CRM, accounting, PMO, audit
  trails, settings and the admin screens need a role with the right permission.
* **Writes** (`POST` / `PUT` / `PATCH` / `DELETE`) need the permission their rule names; a
  write no rule names needs an administrator.
* Public writes are the visitor features: sign-in / sign-up, enquiries and viewing requests
  (`POST /crm/leads`, `/crm/appointments`; 20 per IP per minute), the contact form,
  calculators and analysis tools, the AI endpoints (rate-limited) and signed webhooks.
* `401` means "sign in" (with `WWW-Authenticate: Bearer`), `403` "your role doesn't include
  this". Messaging requests may only act as the signed-in user (`author_id`, `user_id` …
  must match), and a plain agent only reaches their own CRM records.

The full rule table is in
[Security & Operations §2.2](SECURITY_AND_OPERATIONS.md#22-permissions-per-area).

### Auth flow (endpoints)

| Step | Endpoint |
| --- | --- |
| Register | `POST /auth/signup` |
| Verify the sign-up OTP | `POST /auth/verify-otp` |
| Passwordless login | `POST /auth/otp/request` → `POST /auth/otp/verify` |
| Password login | `POST /auth/login` |
| Current account | `GET /auth/me` *(token required)* |
| Refresh token | `POST /auth/refresh` |
| Logout (revoke) | `POST /auth/logout` |
| Set/change password | `POST /auth/password/set` *(token required)* |
| Reset password | `POST /auth/password/reset-request` → `POST /auth/password/reset` |
| Resend OTP | `POST /auth/resend-otp` |
| Policy, environment, demo sign-ins | `GET /auth/config` (`demo_accounts` is empty outside development) |
| Audit trail | `GET /auth/events` *(audit.view)* |
| OTP outbox (dev) | `GET /auth/notifications`, `GET /auth/otps` *(settings.manage)* |

Sessions last 24 hours. Five failed password sign-ins for one account within 15 minutes
lock password sign-in for it (`{"code": "locked"}`); OTP login and password reset still
work. Signing up as `agent` or `developer` creates a `user` account with
`requested_role` set until an administrator grants the role.

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
* **Persistence** — the API works on in-memory stores that are saved to PostgreSQL or
  SQLite a few seconds after each write and restored on start (see
  [Administration §5](ADMINISTRATION_GUIDE.md#5-data-storage--backups)).
* **Request size** — bodies over `PORTAL_MAX_BODY_MB` (30 MB) get `413`.
* **Docs** — `/docs`, `/redoc` and `/openapi.json` are public in development and return
  `404` in production (`PORTAL_EXPOSE_DOCS`).

---

## 4. Key flows

The examples leave out the token for brevity. Public reads work as shown; for everything
else add `-H "Authorization: Bearer $token"` (curl) or `-Headers @{ Authorization = "Bearer $token" }`
(PowerShell) with a token from §2 whose role has the permission.

### 4.1 Properties

```powershell
# list / search
curl "http://127.0.0.1:8000/properties?city=lahore"
# one property
curl "http://127.0.0.1:8000/properties/PROP-0001"
# compare two
curl "http://127.0.0.1:8000/properties/PROP-0001/compare/PROP-0002"
# correct coordinates (properties.manage)
curl -X PUT "http://127.0.0.1:8000/properties/PROP-0001/coordinates" -H "Authorization: Bearer $token" `
  -H "Content-Type: application/json" -d '{"latitude":31.52,"longitude":74.35}'
# houses within 1 km of a school / mosque / mall / hospital / park ... (closest first)
curl "http://127.0.0.1:8000/search?category=house&near=school&near_km=1"
# listings with a feature (matches amenities and description)
curl "http://127.0.0.1:8000/search?feature=solar&min_bathrooms=4"
# nearest school, mosque, hospital, mall, park, transport ... around one listing
curl "http://127.0.0.1:8000/properties/PROP-0001/nearby?radius_km=3"
# listings within 3 km of a named place (nearest ones outside the radius if none inside)
curl "http://127.0.0.1:8000/search?near_place=Rawalpindi%20Medical%20University&near_km=3"
# places in an area, or around a place — with a count
curl "http://127.0.0.1:8000/places/find?kind=mall&area=Bahria%20Phase%208%20Rawalpindi"
curl "http://127.0.0.1:8000/places/find?kind=high%20school&area=DHA%202%20Islamabad"
# population, development level, facilities and nearby housing areas
curl "http://127.0.0.1:8000/areas/profile?area=G-13%20Islamabad"
# DHA master plans: list, phase summary, find text, what's around a point, a close-up image
curl "http://127.0.0.1:8000/masterplans"
curl "http://127.0.0.1:8000/masterplans/ph2"
curl "http://127.0.0.1:8000/masterplans/search?q=jinnah%20blvd&plan=dha%202"
curl "http://127.0.0.1:8000/masterplans/at?place=Paradise%20Park&plan=DHA%20Phase%20II"
curl "http://127.0.0.1:8000/masterplans/view?plan=DHA%20Phase%20II&place=Paradise%20Park"
curl -o plan.png "http://127.0.0.1:8000/masterplans/ph2/snapshot.png?lat=33.53&lon=73.16&radius_m=250"
# a listing (or ?place=…) with the nearest schools, mosques, parks, malls … for a map card
curl "http://127.0.0.1:8000/places/map?listing_id=PROP-0001&kinds=school,mosque,park,mall"
```

`near` takes `school`, `mosque` (or `masjid`), `hospital`, `mall`, `market`, `park`, `bank`,
`restaurant`, `transport` or `fuel`, or a POI category. Nearby places come from the portal's
POI data (`/poi`) and the bundled OpenStreetMap data; place, area and population answers
use the OpenStreetMap and Kontur data (Administration Guide §4.6). Listings carry an
`amenities` list that `/me/listings` and `PUT /properties/{id}` accept.

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

#### Map layers (`gis.manage` for every write)

Every map layer except the base maps is a layer record with a `published` flag (shown on
the public map at all) and `visible` (drawn by default). Guests only get published layers
from `GET /gis/layers` and `GET /gis/layers/{id}` (`404` otherwise), and the built-in
overlay endpoints (`/geo/provinces`, `/geo/districts`, `/geo/places`, `/geo/roads`,
`/geo/water`, `/geo/cities`, `/geo/megaprojects`) answer an empty result with
`"unpublished": true` until the overlay is published. GIS managers always get the data.

| Endpoint | Purpose |
| --- | --- |
| `POST /gis/layers/upload` | Upload a file as a new layer: `{"filename", "content"` (text) or `"content_base64", "name", "layer_type", "entity_type", "entity_id", "style", "published", "visible", "dry_run", "replace_layer_id"}`. Reads GeoJSON, KML, GPX and CSV (lat/lon columns), up to 25 MB / 50,000 features. `dry_run: true` saves nothing and returns `import` stats (feature count, geometry types, bounding box, `swapped_lat_lon`, `inside_pakistan_pct`). `replace_layer_id` replaces that layer's geometry. Shapefiles get a `400` asking for GeoJSON. |
| `POST /gis/layers/publish` | Publish or hide many layers: `{"published": true}` (everything), `{"ids": [...]}`, or `{"scope": "builtin" \| "uploaded" \| "master_plans"}`. Returns `changed`, `now_published`, `layers`. |
| `PUT /gis/layers/{id}` | Edit name, description, type, style, `published`, `visible`, `opacity`, `z_index`, `geojson` (`[lat, lon]` points for Pakistan are flipped). |
| `DELETE /gis/layers/{id}` | Delete a layer. Built-in overlays answer `409` (unpublish them instead). |

```powershell
# check a KML file, then publish everything on a fresh install
curl -X POST "http://127.0.0.1:8000/gis/layers/upload" -H "Authorization: Bearer $token" `
  -H "Content-Type: application/json" -d '{"filename":"zone.kml","content":"<kml>…</kml>","dry_run":true}'
curl -X POST "http://127.0.0.1:8000/gis/layers/publish" -H "Authorization: Bearer $token" `
  -H "Content-Type: application/json" -d '{"published":true}'
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
  -d '{"agent_key":"conversational_buyer_agent","objective":"3-bed in DHA under 3 crore"}'
# runs pause at the human gate by default; approve (crm.manage) to run the write steps:
curl -X POST "http://127.0.0.1:8000/agents/runs/ARUN-0001/approve" -H "Authorization: Bearer $token"
```

Running agents needs sign-in; the approval is recorded under the signed-in user. See the
[Agentic AI Guide](AGENTIC_AI_GUIDE.md#6-approval-gates) for the approval semantics.

### 4.8 Administration

**Base data** (`basedata.manage`): `GET /admin/basedata` (overview), then
`GET|POST /admin/basedata/{cities|schemes|blocks}` and
`GET|PUT|DELETE /admin/basedata/{table}/{id}`. Invalid values get `422`; deleting a city or
scheme still in use gets `409`.

**Property database** (`properties.manage`):

| Endpoint | Purpose |
| --- | --- |
| `GET /admin/properties` | Every listing with every field. Filters `q`, `city_id`, `scheme_id`, `status`, `category`, `use_type`, `featured`, `agent_id`, `located`, `min_price`, `max_price`; `sort` = `updated` \| `created` \| `price` \| `title` \| `size`, `order`, `page`, `page_size`. Returns `rows`, `total`, `pages` and `facets` (counts by status, category, city). |
| `GET /admin/properties/meta` | Choices for the form: statuses, categories, use types, cities, schemes, blocks, agents. |
| `GET /admin/properties/{id}` | One listing. |
| `POST /admin/properties` | Create (`201`). Validated: the scheme must be in the city and the block in the scheme, coordinates inside Pakistan, numbers numeric; marla / kanal / sq ft are kept in step. `400` with the reason otherwise. |
| `PUT /admin/properties/{id}` | Update; returns `property` and the `changed` fields. |
| `DELETE /admin/properties/{id}` | Delete. |
| `POST /admin/properties/bulk` | `{"ids": [...], "action": "feature" \| "unfeature" \| "status" \| "assign_agent" \| "delete", "value"}` (up to 1,000 ids); returns `affected`. |
| `GET /admin/properties/export.csv` | The (filtered by `q`, `city_id`, `status`, `category`) catalogue as CSV. |
| `POST /admin/properties/import` | `{"csv": "...", "dry_run": true}`. Rows with an `id` update, others create; city, scheme, block and agent are matched by name. Returns `rows`, `valid`, `errors` (row number + reason), `would_create`, `would_update`, `saved`. Nothing is saved while `dry_run` is on or any row is invalid. At most 5,000 rows. |

**Storage** (`settings.manage`): `GET /portal/storage` (backend, location, last save, last
error, rows per store) and `POST /portal/storage/flush` (save now; `409` when
`PORTAL_PERSIST=0`).

### 4.9 Assistant: context, knowledge and memory

| Endpoint | Auth | Purpose |
| --- | --- | --- |
| `POST /ai/context` | optional | Everything for one question in one call. Body `{"query", "conversation_id"?, "channel": "chat" \| "voice", "k": 5, "record": true}`. Returns `system_prompt` (the shared prompt with MEMORY and KNOWLEDGE blocks), `prompt_version`, `memory_block`, `knowledge_block`, `knowledge` (`results`, `filters`, `took_ms`), `memory` (`enabled`, `items`, `learned`) and `recent` turns. For a signed-in user (with memory on) the question is remembered; guests get knowledge only. |
| `POST /ai/turn` | signed in | Save a turn (default the assistant's reply): `{"content", "conversation_id"?, "role": "assistant"}`. |
| `POST /ai/knowledge/search` | public | `{"query", "k": 6, "types"?}` (`scheme`, `city`, `mega_project`, `property`, `news`, `guide`, `big_project`). Ranked hits with `cite` (`[1]` …), `tier`, `trust`, `snippet`, `url` and their sources, plus a `context` block with the markers and the parsed `filters` (price, size, bedrooms, type). |
| `POST /ai/web-lookup` | public, rate-limited | `{"question"}` returns `answer`, `sources` (strongest tier first), `best_source_tier`, `trust`, `checked_at`; `"cached": true` when answered within the last 6 hours. Needs `OPENAI_API_KEY`. |
| `GET /me/memory` | signed in | What the assistant remembers about me: `memories` (kind, key, value, source `inferred` \| `explicit`), `recent_turns` (count) and `enabled`. |
| `POST /me/memory` | signed in | `{"text"}`: remember a note (`201`). Notes that look like a CNIC, card number or password get `409`. |
| `DELETE /me/memory/{id}` | signed in | Forget one memory (`404` if unknown). |
| `DELETE /me/memory` | signed in | Forget everything, including recent conversations. |
| `PUT /me/memory/settings` | signed in | `{"enabled": false}` switches memory off (nothing learned or recalled), `true` back on. |

Trust tiers, strongest first: `official` (government / development authority), `verified`
(checked by the portal), `reference` (established reference or news), `listing` (as listed
by an owner or agent), `unverified`.

---

## 5. Real-time: WebSocket

The messaging wing exposes a per-conversation WebSocket:

```
WS /ws/messaging/{conversation_id}?token=<session token>&user_id=<user_id>
```

* `token` is the caller's sign-in token (browsers can't set headers on a WebSocket). No
  valid token, or a `user_id` that isn't the signed-in user (unless an admin), closes the
  socket with **`4401`**. `user_id` defaults to the signed-in user.
* Access to the conversation is **re-checked** on connect; a non-member is closed with
  **`4403`**.
* Events pushed include new messages, edits, reactions, read receipts and action changes.
* The server uses a stdlib pub/sub broker; clients should reconnect with backoff on drop.
* Delivery semantics and reconnect handling are described in the
  [Messaging Guide](MESSAGING_GUIDE.md#10-real-time-websockets).

Example (browser):

```js
const ws = new WebSocket(`ws://127.0.0.1:8000/ws/messaging/CNV-0001?token=${token}`);
ws.onmessage = (e) => console.log("event", JSON.parse(e.data));
ws.onclose = (e) => { if (e.code === 4401 || e.code === 4403) console.warn("not signed in / no access"); };
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
* **OpenAI mode** — with `OPENAI_API_KEY` set, requests go to OpenAI (`OPENAI_MODEL`,
  optional `OPENAI_BASE_URL`). Streaming is passed through.
* **Another OpenAI-compatible server** — set `LLM_BASE_URL`, `LLM_MODEL` and optionally
  `LLM_API_KEY` to send chat to LM Studio, Ollama, vLLM … instead (for testing).

The server pays, so the server decides: chat always uses the configured model (a request
may name another model only if it is listed in `AI_ALLOWED_MODELS`), returns one choice,
and caps the reply at `OPENAI_MAX_OUTPUT_TOKENS` (a client may ask for up to twice that).
`/v1/embeddings` always uses `OPENAI_EMBEDDING_MODEL` and accepts at most 256 inputs or
200,000 characters. `/v1/completions` (legacy) is answered through chat completions and
returned in the `text_completion` shape. These endpoints are public but rate-limited per
caller (`AI_CHAT_PER_MINUTE`).

### Assistant helpers (OpenAI)

| Endpoint | Purpose |
| --- | --- |
| `GET /ai/capabilities` | The chat model (`local` fallback or `upstream` OpenAI) and OpenAI voice status: `voice.{provider, stt, tts, realtime, realtime_model, voice}`. No secrets. |
| `POST /ai/realtime/session` | `{"reply_lang": "auto" \| "ur" \| "en"}` returns `{"client_secret", "expires_at", "model", "calls_url", "voice"}`. The app posts its WebRTC SDP offer to `calls_url` with `Authorization: Bearer <client_secret>` (`Content-Type: application/sdp`). Send the user's bearer token to personalise the agent. Returns `501` without `OPENAI_API_KEY`. |
| `GET /ai/tools` | The assistant's tools in Chat Completions format: `search_listings`, `get_listing`, `request_call`, `my_listings`, `draft_listing`. These are the same tools the live agent gets. The app runs the calls itself, so typed chat and voice notes can search and act. |
| `POST /ai/transcribe` | `{"audio_base64", "mime_type"}` returns `{"text"}`, transcribed by OpenAI `gpt-transcribe` with Urdu and English expected. |
| `POST /ai/speak` | `{"text", "language"}` returns `{"audio_base64", "mime_type": "audio/mpeg"}` from OpenAI text-to-speech. |

The knowledge, context and memory endpoints the assistant uses are in §4.9.

**Chat:** with `OPENAI_API_KEY` set, `/v1/chat/completions` forwards to OpenAI (model
`gpt-6-luna`, or `OPENAI_MODEL`).

### CORS

The API sends CORS headers so the portable desktop app and separately hosted front ends
can call it. Auth is a bearer header (no cookies), so the development default is `*`. In
production (`PORTAL_ENV=production`) there is no default and `*` is ignored: list the
origins in `PORTAL_CORS_ORIGINS` (comma-separated). `PORTAL_ALLOWED_HOSTS` limits the host
names the API answers for.

---

## 7. Rate limits, errors & status codes

| Code | Meaning |
| --- | --- |
| `200` | Success. |
| `400` | Malformed request / invalid parameters. |
| `401` | Missing or invalid bearer token, bad credentials, a bad webhook signature, or `/mcp` without an MCP token / admin session. |
| `403` | Authenticated but not permitted (role lacks the permission, unverified account, acting as another user, another agent's record, restricted channel). |
| `404` | Unknown entity id (also unpublished layers for guests, and API docs in production). |
| `409` | Conflict (e.g. duplicate, cooldown, deleting something still in use or a built-in layer). |
| `413` | Request body over `PORTAL_MAX_BODY_MB`, or an AI input over its size cap. |
| `422` | Validation error (FastAPI / base data). |
| `429` | Rate limited (OTP resend/per-hour caps; messaging per-minute limits; public enquiries 20 per IP per minute; AI calls, with `Retry-After`). |
| `500` | Unexpected error: the body is `{"detail": "Internal server error", "error_id": "…"}`; the server log has the traceback under that id. |
| `4401` / `4403` | WebSocket close codes — not signed in / no access to the conversation. |

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
uv run python smoke_http.py         # real HTTP against :8011 (see the Testing Guide first)
```

The [Testing Guide](TESTING_GUIDE.md) explains coverage, expected output and how to add
new API checks.
