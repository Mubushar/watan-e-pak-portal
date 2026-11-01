# Arz-e-Pak Portal — Administration Guide

This guide is for **portal administrators, DevOps and IT**. It covers deployment,
configuration, access control, security, data and storage, monitoring, and the day-to-day
runbook. For feature walk-throughs aimed at end users, see the
[User Manual](USER_MANUAL.md); for integration surfaces, see the
[MCP Guide](MCP_GUIDE.md) and [API Guide](API_GUIDE.md).

---

## 1. Deployment

### 1.1 Requirements

* Python 3.11+ (the project is developed against the current CPython and run through `uv`).
* Runtime dependencies: `fastapi`, `uvicorn[standard]`, `httpx`, `mcp[cli]`.
* No external database is required: data is saved to a local SQLite file
  (`backend/data/portal.sqlite3`). For PostgreSQL set `DATABASE_URL` and install the
  optional driver (`uv sync --extra postgres`) — see [§5](#5-data-storage--backups).

### 1.2 Install

```powershell
cd backend
uv sync                 # or: uv add fastapi "uvicorn[standard]" httpx mcp[cli]
```

### 1.3 Run modes

| Mode | Command | Notes |
| --- | --- | --- |
| **REST + MCP together** (recommended) | `uv run python main.py` | REST on `:8000/docs`, MCP on `:8000/mcp`, OpenAI facade on `:8000/v1`. |
| **MCP only (stdio)** | `uv run mcp dev server.py` | Opens MCP Inspector on `:6274`. For desktop MCP clients. |
| **Production** | `uvicorn api:app --host 0.0.0.0 --port 8000` | Set `PORTAL_ENV=production`, run **one** worker process, and put an HTTPS reverse proxy in front ([Security & Operations](SECURITY_AND_OPERATIONS.md#4-production-checklist)). |

`main.py` listens on `127.0.0.1:8000` by default, so only this computer can reach it. To
test the Android or iOS app on a real phone, set `PORTAL_HOST=0.0.0.0` (and optionally
`PORTAL_PORT`) in `backend/.env`. Then point the app at `http://<this-pc's-LAN-IP>:8000`.

### 1.4 Ports

| Port | Service |
| --- | --- |
| 8000 | REST + MCP + OpenAI facade (`main.py`). |
| 6274 | MCP Inspector (dev only). |
| 8011 | Live HTTP smoke test (`smoke_http.py`), used by CI. |

---

## 2. Configuration

### 2.1 Environment variables

The portal is configured primarily through the runtime settings surface
([§2.2](#22-runtime-settings)) and environment variables (or `backend/.env`, never
committed; a real environment variable wins) for deployment-level concerns. The full
table is in [Security & Operations §1](SECURITY_AND_OPERATIONS.md#1-environment-variables);
the ones you set first:

| Variable | Default | Purpose |
| --- | --- | --- |
| `PORTAL_ENV` | `development` | `production` switches off demo accounts, exposed OTPs, public API docs, local MCP access and the CORS wildcard, and adds HSTS. |
| `PORTAL_SEED_DEMO` | on in development | Seed the 13 demo accounts. |
| `PORTAL_MCP_TOKEN` | *(empty)* | Bearer token for MCP clients on `/mcp` ([§4.9](#49-mcp-access)). |
| `PORTAL_CORS_ORIGINS` / `PORTAL_ALLOWED_HOSTS` | `*` in development / any | Browser origins and host names the API accepts. List them in production. |
| `PORTAL_AUTH_EXPOSE_OTP` | on in development | Return OTPs as `dev_otp` ([§4.1](#41-auth-policy-group-auth)). |
| `DATABASE_URL` / `PORTAL_DB_PATH` | SQLite in `backend/data/` | Where data is saved ([§5](#5-data-storage--backups)). `PORTAL_PERSIST=0` keeps it in memory only. |
| `PORTAL_MCP_STATELESS` | `1` (true) | `1` runs the MCP HTTP transport **statelessly** (each request independent). `0` keeps session state. |
| `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` | *(empty)* | Send `/v1` chat to another OpenAI-compatible server (LM Studio, Ollama) instead of OpenAI ([§4.5](#45-ai-model-and-voice-for-the-assistant-openai)). |

```powershell
# Example: production-style session
$env:PORTAL_ENV = "production"
$env:PORTAL_MCP_TOKEN = "<long random value>"
$env:PORTAL_CORS_ORIGINS = "https://arzepak.pk"
$env:PORTAL_ALLOWED_HOSTS = "arzepak.pk,api.arzepak.pk"
uv run python main.py
```

### 2.2 Runtime settings

Live tunables are grouped and readable/writable at runtime — no restart needed for most:

* **Read** — `GET /portal/settings` or MCP `portal_settings(action="get")`.
* **Update** — `PUT /portal/settings` or MCP `portal_settings(action="update", updates={...})`.

Groups (see the generated [`reference/SETTINGS.md`](reference/SETTINGS.md) for every key
and the current values):

| Group | Governs |
| --- | --- |
| `auth` | OTP, session and password policy (mirrors `AUTH_CONFIG`). |
| `accounting`, `finance` | Ledger/reporting defaults. |
| `assumptions`, `factor_weights`, `scenarios`, `forecast` | GIS & valuation model inputs. |
| `intelligence` | Property-intelligence scoring. |
| `construction`, `maintenance` | Wing rates and cost factors. |
| `marketing`, `advertising`, `commercial`, `content` | Go-to-market and content defaults. |
| `leasing`, `transactions` | Deal and leasing lifecycle defaults. |
| `agentic` | Autonomy levels, approval-required levels, SLA hours, orchestration cap. |
| `pmo` | Working week (six-day), phase templates and cost factors. |
| `messaging` | Message limits, edit window, attachment size/TTL, retention, rate limits, quiet hours, Telegram and e-mail settings. |
| `tools` | Calculator defaults and area-unit standards. |

---

## 3. Users, roles & permissions (RBAC)

The portal has a four-tier area model — **public → client → staff → admin** — with **19
roles** and **31 fine-grained permissions** (`resource.action`). The server enforces them on
every request (deny by default; see
[Security & Operations §2](SECURITY_AND_OPERATIONS.md#2-security-model)), and the web
portal hides pages and menu items the user's role can't use.

### 3.1 Roles

`user`, `buyer`, `tenant`, `seller`, `landlord`, `investor`, `agent`, `agency_manager`,
`developer`, `valuer`, `accountant`, `finance_manager`, `content_editor`, `ad_manager`,
`customer_support`, `moderator`, `auditor`, `admin`, `super_admin`.

* Public self-registration may only pick from `SIGNUP_ROLES`: `user`, `buyer`, `tenant`,
  `seller`, `landlord`, `investor`, `agent`, `developer`. `agent` and `developer` carry CRM
  and catalogue rights, so those accounts start as a plain `user` with the role
  *requested* (`requested_role`); grant it under **Users & roles** after checking the
  person. Everything else is granted by an administrator.
* A user may hold **several roles**; permissions are the union, plus any directly-granted
  extra permissions. `super_admin` has every permission; `admin` has all but
  `roles.manage`.
* A user whose only CRM role is `agent` sees only their own leads, customers, deals and
  tasks (the account must be linked to a CRM agent).

### 3.2 Permissions

`portal.view`, `portal.publish`, `listings.view`, `listings.manage`, `properties.view`,
`properties.manage`, `basedata.manage`, `projects.view`, `projects.manage`, `gis.view`,
`gis.manage`, `poi.manage`, `aoi.manage`, `crm.view`, `crm.manage`, `accounting.view`,
`accounting.manage`, `finance.view`, `finance.manage`, `payments.view`, `payments.manage`,
`content.view`, `content.manage`, `ads.view`, `ads.manage`, `news.manage`, `users.view`,
`users.manage`, `roles.manage`, `settings.manage`, `audit.view`.

What each one opens:

| Permission | Opens | Roles that have it (besides super_admin) |
| --- | --- | --- |
| `basedata.manage` | Administration › Base data; writes to `/cities`, `/schemes`, `/blocks` | admin |
| `properties.manage` | Administration › Property database; writes to `/properties` | admin, developer |
| `gis.manage` | Administration › GIS layers; every GIS write; unpublished layers | admin, valuer |
| `listings.manage` | images, leasing and maintenance writes | admin, moderator, developer, agency_manager, agent, seller, landlord |
| `crm.view` / `crm.manage` | CRM, marketing, broker, transactions; agent smart actions / approving agent runs | admin, agency_manager, agent, customer_support (both); moderator (view) |
| `accounting.view` / `accounting.manage` | Accounting (`payments.manage` for payments and rent invoices) | admin, finance_manager, accountant (both); auditor (view) |
| `finance.view` / `finance.manage` | Commercial back office | `finance.manage`: admin, finance_manager |
| `projects.view` / `projects.manage` | PMO, big projects | admin, developer |
| `ads.view` / `ads.manage` | Advertising | admin, moderator, ad_manager (both); others view |
| `content.manage` / `news.manage` | Content pages, news | admin, moderator, content_editor |
| `poi.manage` / `aoi.manage` | Points / areas of interest (saving a study area) | admin, developer (POI), valuer (AOI) |
| `users.view` / `roles.manage` | Users & roles | `users.view`: admin, agency_manager, customer_support, auditor |
| `settings.manage` | Portal settings, storage status, OTP outbox, messaging dispatch / purge / moderation | admin |
| `audit.view` | Audit trails, messaging outbox and statistics | admin, finance_manager, auditor |

The authoritative role → permission map is `ROLE_CATALOG` in `backend/auth.py`
(`GET /roles`).

### 3.3 Administering access

| Task | REST | MCP |
| --- | --- | --- |
| List roles / permission catalogue | `GET /roles`, `GET /roles/permissions` | `auth_list_roles`, `auth_permissions` |
| Role summary (members, permissions) | `GET /roles/summary` | `auth_role_summary` |
| Create/update/delete a custom role | `POST/PUT/DELETE /roles/{name}` | `auth_create_role`, `auth_update_role`, `auth_delete_role` |
| Grant/remove a role | `POST/DELETE /users/{user_id}/roles/{role}` | `auth_assign_role`, `auth_revoke_role` |
| Replace a user's role set | `PUT /users/{user_id}/roles` | `auth_set_user_roles` |
| Check effective permissions | `GET /users/{user_id}/permissions` | `auth_user_permissions` |
| Grant a one-off permission | `POST /users/{user_id}/permissions` | `auth_grant_permission` |
| Check a permission | `GET /users/{user_id}/permissions/check` | `auth_check_permission` |
| Suspend a user | `PUT /users/{user_id}` *(status=`suspended`)* | `auth_set_status` |

**Onboarding a staff member:** create the user (admin), assign the appropriate staff role
(`agent`, `finance_manager`, `valuer`, …), and add them to the messaging channels they
need ([§6](#6-messaging-administration)).

**Offboarding (access revocation):** set the user to `suspended`, revoke their roles, and
remove their messaging memberships — see the dedicated
[access-revocation](../backend/README.md) flow in the Messaging Guide's
[Administration section](MESSAGING_GUIDE.md#11-governance). Departing
staff immediately lose channel access and any outstanding signed attachment links remain
scoped to their (revoked) identity. Suspending a user also ends all their sessions.

### 3.4 Administration screens (web portal)

The web portal's **Administration** menu (`/app/admin…`) shows each screen only to roles
with its permission:

| Screen | Route | Permission |
| --- | --- | --- |
| Users & roles | `/app/admin` | `users.view` or `settings.manage` (changing roles needs `roles.manage`) |
| Base data | `/app/admin/base-data` | `basedata.manage` |
| Property database | `/app/admin/properties` | `properties.manage` |
| GIS layers | `/app/admin/gis-layers` | `gis.manage` |

**Base data** — cities, housing societies / societies and blocks / zones
(`/admin/basedata/{cities|schemes|blocks}`): add, edit and delete with validation (unique
names, known approval statuses, sources). A city or scheme that is still in use can't be
deleted (`409`). See `backend/README.md` › *Base data* for where the seed data comes from.

**Property database** — every listing with every field (`/admin/properties*`):

* Search and filter by text, city, scheme, status, category, use type, featured, agent,
  price range and whether it has a map location; sort by updated, created, price, title or
  size; page through the results. Status counts at the top double as filters.
* Add or edit a listing with full validation: the scheme must belong to the city and the
  block to the scheme, coordinates must be inside Pakistan, and the size you type (sq ft,
  marla or kanal) updates the other units.
* **Bulk actions** on the selected rows: feature / unfeature, set status, assign an agent,
  delete.
* **Export CSV** downloads the (filtered) catalogue. **Import CSV** takes the same columns:
  rows with an `id` update that listing, rows without one create a listing; cities,
  schemes, blocks and agents are matched by name. The import always runs as a **dry run**
  first and shows what it would create or update and every row error. Nothing is saved
  while any row is wrong. At most 5,000 rows per file.

**GIS layers** — every map layer except the base maps (`/gis/layers*`):

* **Upload** a GeoJSON, KML (Google Earth), GPX or CSV (latitude / longitude columns) file,
  up to 25 MB and 50,000 features. The drawer reads the file first (dry run) and shows the
  feature count, geometry types, bounding box and how much lies inside Pakistan; points
  given as `[lat, lon]` are flipped to `[lon, lat]` and reported. Shapefiles and KMZ must be
  converted first (QGIS › Export › GeoJSON).
* Edit a layer's name, description, type, style and settings; **replace** its geometry with
  a new file; **download** it as GeoJSON; delete it.
* **Published** decides whether the layer exists on the public map at all; **On by default**
  whether it is drawn before a visitor chooses (visitors switch published layers on and off
  in the map's Layers panel). Unpublished layers are visible only to `gis.manage` users,
  for previewing.
* The **built-in overlays** — listings, featured places, areas of interest, points of
  interest, province and district boundaries, city names, terrain (DTM), water bodies, road
  network, live road overlay and infrastructure mega projects — are layer records too. They
  can be unpublished but not deleted. The master-plan layers are marked *Built from the
  master-plan PDF*; their label geometry is rebuilt from the plan files.
* **On a fresh install every layer starts unpublished**, so the public map shows only base
  maps until you click **Publish all** (or publish layers one by one). The choice is saved
  and survives restarts; overlays added by a later version arrive unpublished.

API equivalents: `POST /gis/layers/upload` (`dry_run`, `replace_layer_id`) and
`POST /gis/layers/publish` (`{"published": true}` for everything, or `ids`, or
`scope`: `builtin` | `uploaded` | `master_plans`).

---

## 4. Authentication & security

### 4.1 Auth policy (group `auth`)

| Setting | Default | Meaning |
| --- | --- | --- |
| `otp_length` | 6 | Digits per one-time code. |
| `otp_ttl_seconds` | 300 | OTP validity (5 min). |
| `otp_max_attempts` | 5 | Wrong-code attempts before the OTP is invalidated. |
| `otp_resend_cooldown_seconds` | 30 | Minimum wait between resends. |
| `otp_max_per_hour` | 10 | Hourly per-identifier cap (rate limit). |
| `session_ttl_hours` | 24 | Bearer-token lifetime; refresh to extend. Sessions are saved, so a restart doesn't sign anyone out. |
| `password_min_length` | 8 | Minimum password length. |
| `pbkdf2_iterations` | 600000 | PBKDF2-SHA256 rounds for new password hashes (`PORTAL_PBKDF2_ITERATIONS`). The count is stored with each salt, so older 120,000-round hashes still verify. |
| `expose_otp` | true in development, false in production | Return codes as `dev_otp`. If `PORTAL_AUTH_EXPOSE_OTP` is unset, this applies only to channels with **no** delivery provider (§4.4). |
| `login_max_failures` | 5 | Failed password sign-ins for one account (`PORTAL_LOGIN_MAX_FAILURES`) … |
| `login_lock_minutes` | 15 | … within this many minutes lock password sign-in for that account for the window (`PORTAL_LOGIN_LOCK_MINUTES`). |
| `channels` | `sms`, `email` | OTP channels. Phone codes go by SMS through `PORTAL_SMS_PROVIDER` (§4.4); WhatsApp is never used for sign-in codes. |

`GET /auth/config` also returns `environment` and, in development only, `demo_accounts`
(the one-click sign-ins the login pages offer).

### 4.2 Flows

* **Signup** → OTP verify (purpose `signup`) → token. `agent` / `developer` sign-ups start
  as `user` with the role requested (§3.1).
* **Passwordless login** → `POST /auth/otp/request` (purpose `login`) → `POST /auth/otp/verify`.
* **Password login** → `POST /auth/login` (401 bad credentials, 403 unverified). Repeated
  failures lock password sign-in for that account (`code: "locked"`, §4.1); OTP login and
  password reset still work, and the lock is logged as `login_blocked`.
* **Refresh / logout** → `POST /auth/refresh`, `POST /auth/logout` (revokes the token).
* **Password reset** → `POST /auth/password/reset-request` → `POST /auth/password/reset`
  (revokes all sessions); signed-in change via `POST /auth/password/set` (ends the user's
  other sessions).
* **Owner account** → `PORTAL_OWNER_USERNAME` / `PORTAL_OWNER_PASSWORD` in `backend/.env`
  create (and on every start re-apply) your own super-admin, independent of the demo
  accounts.

### 4.3 Audit & monitoring

* **Auth audit trail** — `GET /auth/events`.
* **Portal audit trail** — role/assignment/audit views; messaging keeps its own audit log
  (`messaging://audit`). Grant `audit.view` to auditors.
* **OTP outbox** — `GET /auth/notifications` and `GET /auth/otps` (simulated SMS/e-mail
  outbox for demos; need `settings.manage`).
* **Errors** — an unhandled error returns `500` with an `error_id`; search the server log
  for that id to find the traceback.

### 4.4 Delivering OTPs (SMS / e-mail)

Out of the box **no code is sent anywhere**. Each message goes only to the outbox
(`GET /auth/notifications`, status `simulated`), and in development the API returns the
code as `dev_otp` and the apps show a *Test mode* hint. To deliver real codes, configure
`backend/delivery.py` through environment variables or `backend/.env` (template:
`backend/.env.example`, loaded at startup):

| Channel | Provider | Settings |
| --- | --- | --- |
| E-mail | Any SMTP server (Gmail app password, Outlook, Zoho, SendGrid/Mailgun/Brevo SMTP, cPanel) | `PORTAL_SMTP_HOST`, `PORTAL_SMTP_PORT`, `PORTAL_SMTP_USER`, `PORTAL_SMTP_PASSWORD`, `PORTAL_SMTP_FROM`, `PORTAL_SMTP_SECURITY` |
| Mobile | `PORTAL_SMS_PROVIDER=smsgate` (your own Android phone + SIM running [SMS Gateway for Android](https://sms-gate.app)) | `SMSGATE_URL`, `SMSGATE_USERNAME`, `SMSGATE_PASSWORD`, optional `SMSGATE_SIM_NUMBER` (1/2) |
| Mobile | `PORTAL_SMS_PROVIDER=twilio` | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM` or `TWILIO_MESSAGING_SERVICE_SID` |
| Mobile | `PORTAL_SMS_PROVIDER=webhook` (any HTTP SMS gateway) | `PORTAL_SMS_WEBHOOK_URL`, `PORTAL_SMS_WEBHOOK_METHOD`, `PORTAL_SMS_WEBHOOK_HEADERS`, `PORTAL_SMS_WEBHOOK_BODY` (placeholders `{to}`, `{to_digits}`, `{to_local}`, `{message}`, `{code}`) |

What changes once a channel is configured:

* Its codes are **no longer returned** in API responses. Set `PORTAL_AUTH_EXPOSE_OTP=1`
  to keep returning them while testing.
* The outbox stores the message with the code masked, plus `status` (`sent`/`failed`),
  `provider` and `error`.
* If delivery fails, the request returns **502** with `code: "delivery_failed"` and the
  provider's reason. A sign-up whose codes could not be delivered is rolled back, so the
  person can simply try again.
* `GET /auth/config` → `delivery` shows which provider each channel uses (no secrets).

**SMS consent.** Every endpoint that sends a code to a phone number (`/auth/signup` with a
mobile, `/auth/otp/request`, `/auth/resend-otp`, `/auth/password/reset-request`, and
`/auth/login` for an unverified mobile account) needs `"sms_consent": true`. Without it the
API answers **422** `code: "sms_consent_required"`; with it, the consent is logged as
`sms_otp_consent` in `GET /auth/events`. E-mail codes need no consent. The apps show the
consent checkbox under the mobile field and enable *Send code* only once it is ticked.

**Phone number.** Users enter the full number with country code (`+92 300 1234567`,
`+971 50 123 4567`); a local `0300 1234567` is still read as Pakistan. In the Android app,
*Use a number from this phone* opens Google's Phone Number Hint picker with the SIM's
numbers (no phone permission; the picked number is only a suggestion until the code proves
it). When the code SMS arrives, Android asks *Allow Watan-e-Pak to read this message?*
(SMS User Consent API, no SMS permission) and fills in the code if the user allows it. On
iOS the keyboard offers the code from Messages; on the web the user types it.

#### SMS Gateway for Android (`smsgate`) setup

1. Take a spare Android phone with an active SIM and an SMS bundle; keep it charged and
   online. Its SIM number is the sender users will see.
2. Install **SMS Gateway for Android** from <https://sms-gate.app> (Google Play or the APK
   from its GitHub releases) and grant it SMS permission.
3. Choose a mode in the app:
   * **Local server** — the backend reaches the phone on the same network (or a VPN):
     `SMSGATE_URL=http://<phone-ip>:8080/message`. Give the phone a fixed IP on the router.
   * **Cloud server** — the backend is on the internet and the phone is not reachable
     directly: `SMSGATE_URL=https://api.sms-gate.app/3rdparty/v1/message`.
4. Copy the username and password the app shows into `SMSGATE_USERNAME` / `SMSGATE_PASSWORD`
   in `backend/.env`, set `PORTAL_SMS_PROVIDER=smsgate`, and restart the backend.
5. Check `GET /auth/config` → `delivery.sms` is `smsgate`, then sign up with your own number.

Each code costs one SMS from that SIM's package. Keep volumes to OTPs: mobile operators may
block SIMs that send bulk or marketing traffic. For higher volume or a branded sender ID use
a Pakistani bulk-SMS company through `webhook` instead.

### 4.5 AI model and voice for the assistant (OpenAI)

OpenAI is the assistant's only AI provider (`backend/openai_facade.py`,
`backend/openai_voice.py`). Set `OPENAI_API_KEY` in `backend/.env` (template:
`backend/.env.example`). Without it the assistant runs in **basic mode**: answers come
from listing search and voice is off; the app shows a notice.

| Feature | OpenAI API | Setting (default) |
| --- | --- | --- |
| Typed chat, voice-note replies and web look-ups | Chat completions / Responses (web search) | `OPENAI_MODEL` (`gpt-6-luna`), `OPENAI_WEB_MODEL` |
| **Live voice agent** | Realtime API (speech-to-speech, WebRTC) | `OPENAI_REALTIME_MODEL` (`gpt-realtime-2.1-mini`) |
| Voice notes and live captions | Speech-to-text, with `languages: ["ur","en"]` so Urdu comes back in Urdu script and not Hindi | `OPENAI_TRANSCRIBE_MODEL` (`gpt-transcribe`) |
| Voice-note replies | Text-to-speech | `OPENAI_TTS_MODEL` (`gpt-4o-mini-tts`) |
| Voice | Built-in voice, or your own custom voice | `OPENAI_VOICE` (`marin`), `OPENAI_VOICE_ID` (`voice_…`) |

**How the live agent connects.** The app calls `POST /ai/realtime/session`. The backend
mints a 10-minute client secret (`/v1/realtime/client_secrets`) carrying:

- the agent's instructions, including the signed-in user's name and role;
- the reply language (`auto`, `ur` or `en`);
- the voice, the semantic turn detection that lets users interrupt, and Urdu/English captions;
- five tools: `search_listings` (also by features such as *solar*, and by places nearby: *school ke paas*, *masjid ke qareeb*, *near a mall*), `get_listing` (shows the listing's card with *Open listing* and *Request a call*, and returns its amenities and nearby places), `request_call` (sends the owner / agent a call-back request as a CRM lead, from the signed-in user's account), `my_listings`, `draft_listing`.

The app then opens a WebRTC call directly to OpenAI with that secret. The real API key
never leaves the server. The app runs the tool calls against this backend, using the
user's own session, and returns the results to the model. One call can last at most 60
minutes.

**Nearby places.** "Near a school / mosque / mall" answers and the listing page's *Nearby*
section use the portal's POI data, not a map service. A listing far from any POI gets no
nearby answer, and the agent says so rather than guessing. Add POIs for each area you list
in (`POST /poi`, or the `poi_*` MCP tools) with a name, category (`education`, `worship`,
`health`, `shopping`, `park`, `bank`, `restaurant`, `transport`, `fuel`, `government`) and
coordinates. Listings also need coordinates.

**Custom voice.** OpenAI creates voices from your own recordings only for eligible
customers; you request access through OpenAI sales. You record a fixed consent phrase
(there is no Urdu phrase, so use the English one) and upload a 10–30 second sample. Put
the resulting `voice_…` id in `OPENAI_VOICE_ID`. OpenAI requires telling listeners that
the voice is AI-generated.

**Cost.** The defaults are OpenAI's low-cost models: `gpt-6-luna` for text (the cheapest
current model with function calling) and `gpt-realtime-2.1-mini` for live voice (about a
third of `gpt-realtime-2.1`'s audio price). `gpt-transcribe` is kept because it accepts
`languages: ["ur","en"]`; `gpt-4o-mini-tts` is the cheapest text-to-speech model.
Realtime is billed per audio token, speech-to-text per minute and text-to-speech per
token. Chat replies are capped at `OPENAI_MAX_OUTPUT_TOKENS` (800) and web look-ups at
1,200 output tokens; the app hangs up a live call after `AI_LIVE_MAX_MINUTES` (8). Set a
monthly budget on the OpenAI project as well. For a quality upgrade, set
`OPENAI_REALTIME_MODEL=gpt-realtime-2.1` (and optionally a larger `OPENAI_MODEL`).

**Cost protection.** Every endpoint that spends OpenAI credit is rate-limited per caller.
These are `/v1/chat/completions` and `/v1/completions` (when proxying), `/ai/transcribe`,
`/ai/speak` and `/ai/realtime/session`. A caller is the signed-in user, or the IP address
for a guest. Over the limit, the API answers `429` with a `Retry-After` header. Counters
are kept in memory and reset on restart.

| Setting | Default | Meaning |
| --- | --- | --- |
| `AI_CHAT_PER_MINUTE` | 30 | Chat requests (typed messages, voice-note replies). `0` = no limit. |
| `AI_VOICE_PER_MINUTE` | 30 | Speech-to-text and text-to-speech calls. |
| `AI_LIVE_PER_HOUR` | 6 | Live voice-agent calls started. |
| `AI_LIVE_MAX_MINUTES` | 8 | The app ends a live call after this many minutes. `0` = no limit. |
| `OPENAI_MAX_OUTPUT_TOKENS` | 800 | Reply cap for chat when the client sets none; a client may ask for at most twice this. `0` = no cap. |
| `AI_ALLOWED_MODELS` | *(empty)* | The server always uses `OPENAI_MODEL`; list extra models here (comma-separated) that callers may name on `/v1`. |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | The only model `/v1/embeddings` uses (at most 256 inputs / 200,000 characters per call). |
| `AI_REQUIRE_SIGNIN` | 0 | `1` = guests get `401` and must sign in to use the AI. |
| `AI_TRUST_PROXY` | 0 | `1` only behind your own reverse proxy: guests are told apart by `X-Forwarded-For`. Otherwise anyone could fake that header to dodge the limits. |

There are also fixed size caps:

- voice notes: 25 MB (OpenAI's limit);
- text to speak: 4,000 characters;
- chat: 60 messages or 200,000 characters per request.

Requests over a cap get `413`.

If OpenAI itself refuses a request, the app gets a readable error:

- OpenAI rate limit or exhausted quota: `429`;
- rejected API key: `502` "check OPENAI_API_KEY";
- OpenAI unreachable: `502`.

### 4.6 Places, areas and population (what the assistant knows about a location)

The assistant answers questions like these:
- "Which malls are in Bahria Phase 8?"
- "How many high schools are in DHA 2 Islamabad?"
- "I need a room near Rawalpindi Medical University."
- "How developed is G-13, and how many people live there?"

It answers from data bundled in `backend/geodata/` for Islamabad/Rawalpindi, Lahore and
Karachi:

| File | What | Source |
| --- | --- | --- |
| `places.json.gz` | ~12,000 named places: schools, colleges, universities, hospitals, clinics, mosques, malls, markets, parks, banks, restaurants, stations, fuel | OpenStreetMap |
| `areas.json.gz` | ~2,000 sectors, phases, neighbourhoods and housing societies, with outlines and estimated population | OpenStreetMap, Nominatim |
| `population.json.gz` | people per ~0.74 km² hexagon | Kontur Population 2023 |

The agent's tools:
- **`find_places`** (`GET /places/find`): lists and counts places of a kind inside an area
  or around a place.
- **`area_info`** (`GET /areas/profile`): gives an area's population estimate, density, size
  and development level (from population density and mapped facilities), plus counts of
  schools, mosques, hospitals, malls and parks, notable places, portal listings with
  average prices, and nearby housing areas with their population.
- **`search_listings`** with `near_place`: finds listings around a named place. When none
  are close enough, it returns the nearest ones.
- **`show_map`** (`GET /places/map`): puts a map card in the chat. It shows a listing, or a
  named place, with the nearest schools, mosques, parks, malls and hospitals as coloured
  markers, plus an "Open in Google Maps" link. On the outskirts the radius widens until a
  few places show. Each listing page has the same map.
- **`web_lookup`** (`POST /ai/web-lookup`): uses OpenAI web search, with sources, for facts
  the data can't hold, such as approval authority, possession status or news. It asks for
  official sources first (`.gov.pk`, `.gop.pk`, `.gos.pk`, `.gkp.pk`, SBP, DHA), then
  established news, ranks the returned sources by trust tier (`best_source_tier`), and
  answers the same question from a cache for 6 hours (`"cached": true`).
- **`knowledge_search`** (`POST /ai/knowledge/search`): the portal's own knowledge base, with
  citations (§4.10).

Area names are matched loosely, so "DHA 2", "Phase-VIII" and "G13" work. A city word
narrows the search. Names the bundled data doesn't know are looked up on Nominatim when
`GEO_ONLINE_LOOKUP=1`.

**Your own society data.** Staff can record what maps can't know: `development_status`,
`approval_authority`, `possession_status`, `utilities` and `population` on a housing society
(`update_housing_scheme` MCP tool, or `PUT /schemes/{id}`). `area_info` includes them
whenever the scheme matches.

**Map tiles.** Map cards use OpenStreetMap's tile server, which is fine for testing and
light use. Its usage policy forbids heavy traffic, so before launch set `MAP_TILE_URL` and
`MAP_TILE_ATTRIBUTION` to a tile provider's (MapTiler, Stadia Maps, Thunderforest …).

**Accuracy.** Counts cover places that volunteers have mapped on OpenStreetMap, so small
or new ones can be missing. Population is a modelled estimate, not a census. The agent is
told to say both.

**Refreshing the data** (a few times a year):

```powershell
cd backend
# 1. Download "Pakistan: Population Density for 400m H3 Hexagons" (Kontur, CC BY 4.0) from
#    data.humdata.org and unzip it, then:
uv run python geodata/build_geodata.py --kontur C:\path\kontur_population_PK_20231101.gpkg
```

To add a city, add its bounding box to `REGIONS` (and well-known societies to
`SOCIETIES`) in `geodata/build_geodata.py`, then rebuild.

**Licences.** Show the attribution wherever the data appears; the app's Profile page
already does. Map data © OpenStreetMap contributors (ODbL 1.0). Population © Kontur
(CC BY 4.0).

### 4.7 DHA master plans (GIS layers and the assistant)

The portal can load the DHA Islamabad-Rawalpindi master plans: Phases I, II, III, V and VI,
ME-1 & ME-2, and River View North and South. It uses the PDFs together with their
georeferenced images (ground control points; about 10–20 m absolute accuracy).

**What gets built** (into `media/masterplans`, or `MASTERPLANS_DIR`):
- **Labels on the ground.** Every text label in each PDF (about 100,000) is placed at its
  real location and classified:
  - sector / block, plot number, plot size, road and width;
  - park, mosque, school, health, commercial, apartments, club, gate, lake / nullah;
  - parking, amenity plots, infrastructure marks and dimensions.

  The PDF is matched to the georeferenced image, then each label goes from PDF points to
  image pixels and through the control-point fit to latitude and longitude.
- **Map tiles** of each plan (zoom 12–17), shown as a switchable overlay on every map card.
- **Close-up pieces.** The full-resolution plan is cut into pieces, so the assistant can
  share a readable section around any point.
- **Outline and area statement.** The plan outline, plus the sheet's legend and
  area-statement text.

**GIS registration.** At start-up each plan becomes a housing society (`DHA Phase II`, …)
with these GIS layers:
- `boundary`: the plan outline;
- `master_plan`: the outline plus the tile URL in `image_url`;
- three `annotation` layers with the PDF text:
  - *names & facilities*, visible;
  - *plot numbers & sizes*, hidden by default;
  - *engineering marks & dimensions*, hidden by default.

They work with all existing `/gis` endpoints and MCP tools. Like every map layer they
start unpublished; publish them under Administration › GIS layers (§3.4). Turn this off
with `MASTERPLANS_GIS=0`.

**The assistant's tools:**
- **`master_plan`** (`GET /masterplans/{key}`, `/masterplans/search`, `/masterplans/at`):
  - a phase summary: plot sizes with kanal/marla equivalents, sectors and blocks, named
    roads, mosques, parks, schools, commercial areas, clubs, gates and the area statement;
  - label search;
  - what the plan shows around a listing or place.
- **`show_plan`** (`GET /masterplans/view`, `/masterplans/{key}/snapshot.png`): puts a
  close-up of the plan in the chat, with a marker and scale bar, plus a map with the plan
  overlaid.
- **Web facts per phase** (`POST /masterplans/knowledge/refresh`) collect possession,
  development, approvals, facilities and news from the web, with sources. They're saved to
  `knowledge.json` and included in phase summaries. For live questions the agent also uses
  `web_lookup`.

**Building / refreshing** (after DHA issues a new plan, or to add GCPs):

```powershell
cd backend
uv run --with pymupdf --with numpy python masterplans/build_masterplans.py --maps "C:\path\to\Maps"
# optional: only some plans, e.g. --plans ph2,ph5
```

The `Maps` folder holds the PDFs and `Georeferenced\` (per plan: `_source.png`,
`_EPSG3857.png` + `.pgw`, `_gcps.csv`, plus `accuracy_report.json`). To add another plan,
georeference it the same way and add an entry to `PLANS` in the script. The output is
large (map tiles and image pieces) and is not committed to git. Build it on each server,
or copy the folder there.

**Accuracy and wording.** The agent says that answers come from the master plan, that
positions are approximate (about 10–20 m), and that what is built may differ. Plot sizes in
marla use DHA's 225 sq ft per marla (1 kanal = 4,500 sq ft).

**Permission.** The plans are © DHA Islamabad-Rawalpindi. Showing them to customers in a
commercial app may need DHA's permission. Check before launch.

### 4.8 Advertising (earning from ads)

The apps carry ad slots on Home (rotating banners), Explore (one card after every 6
listings), each listing page and Profile ("Advertise with Arz-e-Pak"). Each slot first
shows a **sponsored ad you sold directly**. If no advertiser has booked that slot, it
falls back to **Google**:

| App | Fallback | Why |
| --- | --- | --- |
| Web build (hosted site) | Google AdSense | AdSense is only allowed on web sites. |
| Android / iOS | Google AdMob banner above the tab bar | Google's ad network for apps. |
| Windows / macOS desktop | none (sponsored ads only) | Google allows neither network in desktop apps. |

Every ad is labelled *Sponsored*. The Assistant, sign-in and listing form screens never
show ads.

**Direct (sponsored) ads.** These usually pay the most because you keep all the money.
Sell the space to developers, banks, builders, solar and interior companies. Then create
the ad (`POST /ads`, or the `ad_*` MCP tools):

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/ads" -ContentType "application/json" -Body '{
  "title": "Spring offer", "headline": "Solar for every home", "advertiser": "Your client",
  "category": "solar_energy", "slot": "hero", "cta_label": "Get a quote", "cta_url": "https://client.example",
  "pricing": "cpm", "rate": 400, "budget": 200000, "city": "Lahore"}'
```

- `slot`: `hero` (Home carousel), `banner` (second Home banner), `infeed` (Explore),
  `sidebar` (listing page), `footer` and `newsletter` (web portal).
- `pricing`: `flat` (a fixed fee you invoice yourself), `cpm` (`rate` PKR per 1,000 views)
  or `cpc` (`rate` PKR per click). Spend builds up as the apps report views and clicks.
  The ad pauses itself when it reaches `budget`.
- A view is counted when at least half the ad has been on screen for a second. Each
  viewer counts once per ad per 10 minutes (views) or 30 minutes (clicks), so refreshing
  doesn't bill the advertiser twice.
- `GET /ads/performance` and `GET /ads/report` give the views, clicks, CTR and spend to
  invoice from. Optional targeting: `city`, `scheme`, `lang`, `valid_from` / `valid_until`.
- The ads seeded with the portal are **samples**: fictional advertisers, links to
  example.com, marked *Sample* in the app. Pause or delete them
  (`PUT /ads/{id}` with `"status": "paused"`) once real advertisers are booked.

**Google AdSense (web build).**
1. Host the web build on your own domain and apply at adsense.google.com. Google reviews
   the site, and needs a privacy policy page.
2. Set `ADS_ADSENSE_CLIENT=ca-pub-…` and create one display ad unit each for
   `ADS_ADSENSE_SLOT_HOME`, `_EXPLORE` and `_DETAIL`.
3. Publish `ads.txt` at the root of the site. `GET /ads.txt` returns the exact line.

**Google AdMob (Android / iOS).**
1. Create the two apps at admob.google.com and a *banner* ad unit for each.
2. Replace Google's **sample** app ids, which only show test ads:
   - Android: `com.google.android.gms.ads.APPLICATION_ID` in
     `portable/android/app/src/main/AndroidManifest.xml`;
   - iOS: `GADApplicationIdentifier` in `portable/ios/App/App/Info.plist`.

   Then rebuild the apps.
3. Set `ADS_ADMOB_ANDROID_BANNER` and `ADS_ADMOB_IOS_BANNER`, then `ADS_ADMOB_TESTING=0`.
   Leave testing on (the default) while developing: test ads are safe, but they earn nothing.
4. Publish `app-ads.txt` on the developer website listed in your store pages. AdMob shows
   the line to use.

The apps ask for consent where the law needs it, using Google's consent form (EU/UK).
iOS also asks the tracking question. Never click your own ads: Google bans accounts for it.

Creating, editing and deleting ads needs `ads.manage`; reading campaigns and reports needs
`ads.view`. Only the apps' view / click events (`/ads/{id}/event`, `/ads/{id}/track`) and
the active-ad feed are public.

### 4.9 MCP access

`/mcp` exposes every portal tool, so it is not public. A client needs one of:

* `Authorization: Bearer <PORTAL_MCP_TOKEN>` — set a long random token in `backend/.env`
  and put it in the MCP client's configuration;
* the bearer token of a signed-in `super_admin` / `admin` (the web portal's MCP console and
  tool runner use this, and are shown to administrators only);
* in development, with no token set, a local client on `127.0.0.1` that sends no browser
  `Origin` header (`PORTAL_MCP_LOCAL`, on by default outside production).

Other callers get `401`. The [MCP Guide §5](MCP_GUIDE.md#5-identity--auth) shows the client
configuration.

### 4.10 The assistant's knowledge, memory and prompt

* **Knowledge base** (`backend/knowledge.py`) — fast BM25 search over listings, housing
  schemes (with approval status and sources), cities, mega projects, big projects, news and
  the guide pages, rebuilt automatically when the data changes. It understands crore / lakh /
  arab, marla / kanal / sq ft, bedrooms, Urdu script and Roman Urdu. Every hit carries a
  `[n]` citation and a **trust tier** (`backend/sources.py`): `official` (government and
  development authorities), `verified` (checked by the portal), `reference` (established
  references and news), `listing` (submitted by an owner or agent) and `unverified`
  (everything else, including the sample news). Keep scheme sources in **Base data**
  accurate: they decide the tier.
* **One system prompt** (`backend/prompts.py`, `PROMPT_VERSION`) for the web portal, the
  app and voice. `POST /ai/context` returns it together with the knowledge hits and what the
  assistant remembers about the user, in one call.
* **Memory** (`backend/memory.py`) — per signed-in user and private to them (not visible to
  other users or to admins): the last turns of each conversation (14 days, at most 200) and
  long-term facts (budget, cities and schemes, type, size, bedrooms, buying or renting,
  language, and notes the user asked to keep; at most 150). It never stores CNIC, card or
  bank numbers or passwords. Users list, delete, clear or switch it off through
  `/me/memory`. Guests get no memory. Memory is saved with the rest of the data (§5).

---

### 4.11 Project inventories (China Center, Skyra Tower, Goldcrest Breeze …)

New towers and mixed-use projects that sell units off-plan live in `backend/geodata/pk_project_inventory.json`, built from each project's official website by `backend/build_project_inventory.py` (raw inventories in `geodata/project_sources/`). At every start `project_inventory.sync()` makes the portal match the file:

- each project is a **Big project** with developer, address, unit types, price range, payment plan, offer, units available, the date the inventory was checked and its sources, shown on `/projects?project=<id>`;
- every **available unit is a listing** linked to its project (`project_id`, `project_unit`), with its own size, price, floor, payment schedule and the project's real photos and plan; `/properties?project=<id>` lists them;
- a unit that leaves the developer's inventory is marked **sold** (never deleted);
- the projects also appear on the map's mega-projects layer as "High-rise & mixed-use projects".

To refresh: update the inventories, run `uv run python build_project_inventory.py`, restart. Prices and availability always say "confirm at booking".

### 4.12 Real, credited photos for reference data

Cities, housing societies and infrastructure projects show real photos from Wikimedia Commons, taken from each record's Wikipedia article (checked against its coordinates) with author and licence; `backend/geodata/pk_seed_media.json` is built by `uv run python build_seed_media.py` and attached at start (`seed_media.apply()`), never replacing images an admin added. Records without a matching article keep no image rather than a made-up one. Credits appear on the cards (CC BY-SA requires them). The landing page uses Islamabad photos (Faisal Mosque with the Margalla Hills, Pakistan Monument, Daman-e-Koh), credited in `frontend/src/pages/public/home/Landing.tsx`. New seed data must use real images from its own source.

### 4.13 Portal order (Islamabad first)

`backend/priority.py` sets the order every list uses — cities: Islamabad, Rawalpindi, Lahore, Karachi, then by population; housing societies: DHA Islamabad-Rawalpindi phases V, III, 4, VI, II, I, then Bahria Town phases 8, 7, 1-6, then other DHA, then Islamabad's other popular societies, then the rest of the country by city and popularity. `/cities`, `/schemes`, `/hierarchy`, base data, admin forms and the default listing order follow it; change it in that one file.

## 5. Data, storage & backups

### 5.1 Durable storage — read this first

The portal works on in-memory stores for speed, and `backend/storage.py` saves every one of
them to a database, so **data survives a restart**:

* **Where** — PostgreSQL when `DATABASE_URL=postgresql://…` is set and the optional driver
  is installed (`uv sync --extra postgres`); otherwise a SQLite file,
  `backend/data/portal.sqlite3` (`PORTAL_DB_PATH`; git-ignored).
* **First run** — the sample data is seeded and saved. **Every later start** loads the saved
  data instead of the seed.
* **When** — a few seconds after any write request (`PORTAL_DB_FLUSH_SECONDS`, default 3),
  once a minute regardless, and at shutdown. Only changed items are written.
* **Status** — `GET /portal/storage` (backend, location, last save, last error, rows per
  store); `POST /portal/storage/flush` saves now. Both need `settings.manage`.
* **Off** — `PORTAL_PERSIST=0` keeps everything in memory (the test suite does this).
* Run **one** backend process; several workers would each keep their own copy.

How rows are stored, what is skipped, and what happens when a store can't be loaded are in
[Security & Operations §3](SECURITY_AND_OPERATIONS.md#3-durable-storage). The
`migrate_to_postgres.py` toolkit ([Data Migration Guide](DATA_MIGRATION_GUIDE.md)) is a
separate export into a relational schema for reporting; the running portal doesn't read it.

### 5.2 Object storage for attachments

Attachments are **references** (a controlled `storage key` or a link to an existing portal
record) — the file bytes live in private object storage, never in the database or the
message body. The portal hands out **HMAC-signed, expiring, permission-checked links**
(default TTL 30 minutes). Configure the store with:

* a private bucket (no public access),
* server-side encryption,
* lifecycle rules aligned with the retention policy ([§6](#6-messaging-administration)).

### 5.3 Backups & retention

| Concern | Policy |
| --- | --- |
| Database backups | SQLite: flush, then `sqlite3 backend/data/portal.sqlite3 ".backup <file>"` daily. PostgreSQL: `pg_dump` of `portal_rows` and `portal_kv`, plus daily full + point-in-time recovery. Also back up `backend/media/uploads/` (listing photos). |
| Object storage | Versioned bucket with lifecycle/expiry rules. |
| Message retention | `retention_days_default` = **1095 days (3 years)**; configurable per policy. |
| Deletion | Per-conversation deletion and retention enforcement; deletions are audited. |
| Restore | Test a restore into a staging instance quarterly. |

---

## 6. Messaging administration

The messaging wing is governed by the `messaging` settings group (see the generated
[`reference/MESSAGING.md`](reference/MESSAGING.md) for catalogs and limits).

### 6.1 Channels

Default channels are **Sales**, **Property Verification**, **GIS & Mapping**,
**Customer Support**, **Announcements**, and a **restricted Management** channel. The
Management channel (and any channel marked `restricted`) is limited to `ADMIN_ROLES`
(`owner`, `super_admin`, `admin`, `manager`, `management`, `director`, `principal`). Staff
whose role is an admin role may read any *non-restricted* channel without joining.

| Action | REST |
| --- | --- |
| List / create / update channels | `/messaging/conversations` (kind `channel`) |
| Add / remove members | `/messaging/conversations/{id}/members` |
| Archive / lock a conversation | `/messaging/conversations/{id}` |

### 6.2 Notification delivery

Notifications go through a **queue → dispatcher → outbox** pipeline. The in-process
dispatcher (`dispatch_pending`) renders per-channel payloads respecting **per-user,
per-category preferences** and **quiet hours** (urgent notifications are exempt), then
marks each item `sent` / `deferred` / `failed` and writes it to the outbox. In production,
**run the same queue from a background worker** and hand e-mail/Telegram payloads to a
provider — that is the documented seam. `GET /messaging/outbox` shows the queue;
`messaging://outbox` is the same over MCP.

Categories: `mention`, `direct`, `channel`, `property`, `lead`, `approval`, `task`,
`system`. Users choose channels per category (in-app / e-mail / Telegram).

### 6.3 E-mail

Configured under `messaging.email` (`from`, `reply_to`, digest mode, subject prefix).
E-mail payloads contain **short text plus an authenticated deep link** back to the portal
— **never document content**.

### 6.4 Telegram (optional, opt-in)

Telegram is a *complementary* alert channel, never the primary workspace.

| Setting | Value |
| --- | --- |
| `telegram.enabled` | true |
| `telegram.bot_name` | `ArzPakPortalBot` |
| `telegram.max_text` | 320 chars |
| `telegram.link_code_ttl_minutes` | 15 |
| `telegram.attach_allowed` | **false** — documents never go through Telegram |

Users opt in by sending `/start <link_code>` to the bot; commands are `/stop` (opt out),
`/mute`, `/unmute`, `/digest`, `/status`. Every alert is sanitised to short text plus an
authenticated deep link (`/messaging/portal`); **no confidential data is sent via
Telegram**. When you register the bot's webhook with Telegram (`setWebhook`), pass a
`secret_token` and put the same value in `PORTAL_TELEGRAM_WEBHOOK_SECRET`; updates without
it are then refused with `401`.

### 6.5 Moderation, retention & revocation

* **Reports** — users can report a message; moderators act with `dismiss`,
  `delete_message`, `mute_author` or `escalate`.
* **Audit** — every membership change, deletion, moderation action and dispatch is
  recorded (`messaging://audit`).
* **Retention** — configured per policy (default 3 years).
* **Access revocation** — suspending a user and removing memberships revokes channel
  access; outstanding signed links are identity-scoped and expire on their own.

---

## 7. Monitoring & health

| Signal | Where |
| --- | --- |
| Portal health (store counts, subsystem status) | MCP `portal_health`, `GET /portal/health`, `portal://health` |
| Portal statistics | `portal_statistics`, `/portal/statistics`, `portal://statistics` |
| Portal catalog (all tools/resources, grouped) | `portal_catalog`, `/portal/catalog`, `portal://catalog` |
| Messaging statistics | `messaging://statistics`, `/messaging/statistics` |
| Messaging audit trail | `messaging://audit` |
| Portal activity (recent events) | `portal_activity` |
| Durable storage (last save, errors, rows per store) | `GET /portal/storage` |
| Sign-ins, failures and lockouts | `GET /auth/events` |

`portal_health` reports counts for the messaging stores (`msg_*`) alongside every other
subsystem, so a single call tells you whether a wing failed to seed.

---

## 8. Languages & themes

* **Languages** — HTML pages accept `?lang=xx`; strings are resolved by the GIS/i18n
  layer (English, Urdu and others). `gis://languages` lists what's available.
* **Themes** — `?theme=auto|light|dark`; the choice is remembered in the browser.
* **News ticker** — driven by the `news` group; manageable via `news.manage`.

---

## 9. Optional dependencies

Heavy or licensed capabilities do **not** silently degrade or fake output. They return a
structured **`requires_optional_dependency`** descriptor naming the missing package, e.g.:

| Capability | Would need |
| --- | --- |
| High-fidelity PDF rendering | a PDF library (e.g. PyMuPDF) |
| Raster/vector reprojection & analysis | GeoPandas / GDAL |
| Image manipulation (thumbnails, staging) | Pillow |

This lets a caller detect the limitation and choose a fallback instead of receiving
plausible-but-wrong data.

---

## 10. Security hardening checklist

The full list, with the reasons, is the
[production checklist](SECURITY_AND_OPERATIONS.md#4-production-checklist). In short:

- [ ] Set `PORTAL_ENV=production` (no demo accounts, no exposed OTPs, API docs hidden,
      no local MCP access, HSTS).
- [ ] Set `PORTAL_MCP_TOKEN`, `PORTAL_CORS_ORIGINS` and `PORTAL_ALLOWED_HOSTS`.
- [ ] Terminate TLS at an HTTPS reverse proxy; never expose `main.py` directly to the
      internet. Set `PORTAL_TRUST_PROXY=1` only behind it.
- [ ] **Rotate every API key or password that was ever pasted into `backend/.env` comments,
      `.env.example`, a ticket or a chat.**
- [ ] Create your owner account (`PORTAL_OWNER_USERNAME` / `PORTAL_OWNER_PASSWORD`) and
      remove or suspend any demo accounts carried over from a development database.
- [ ] Set the webhook secrets (`PORTAL_WHATSAPP_APP_SECRET`,
      `PORTAL_TELEGRAM_WEBHOOK_SECRET`, `PORTAL_CRM_WEBHOOK_SECRET`).
- [ ] Use PostgreSQL (`DATABASE_URL`) or back up the SQLite file daily; test a restore.
      Run one backend process.
- [ ] Publish the map layers you want public (§3.4).
- [ ] Keep attachments in a private, encrypted bucket; audit signed-link TTLs.
- [ ] Run the notification dispatcher as a background worker with provider credentials
      injected via environment/secret store (never committed).
- [ ] Grant the principle of least privilege using roles + permissions; review `audit.view`
      and `settings.manage` holders; grant requested `agent` / `developer` roles only after
      checking the person.
- [ ] Review messaging retention and moderation policy with legal/compliance.
- [ ] Replace AdMob's sample app ids and set `ADS_ADMOB_TESTING=0` only in release builds (§4.8).
- [ ] Confirm DHA's permission to show its master plans to customers (§4.7).

---

## 11. Runbook

| Symptom | Likely cause | Action |
| --- | --- | --- |
| `ModuleNotFoundError` on start | Wrong working directory or deps not installed | Run from `backend/`; `uv sync`. |
| Port 8000 address in use | Stale process | Stop it or use another port; `smoke_http.py` uses 8011. |
| Data resets after restart | `PORTAL_PERSIST=0`, or the database couldn't be opened | `GET /portal/storage`; check the startup log line `storage: …` ([§5](#5-data-storage--backups)). |
| `GET /portal/storage` lists a store under `frozen` | Its saved rows couldn't be loaded (e.g. after a model change); it runs on sample data and is never written | Fix the cause, restart; the saved rows are untouched. |
| PostgreSQL configured but SQLite used | `psycopg` not installed | `uv sync --extra postgres`, restart. |
| A wing shows zero items in `portal_health` | Seeding failed for that wing | Check startup logs; the `_seed_*` routine for that wing. |
| User can't see a page/channel | Missing role/permission or membership | Review [§3](#3-users-roles--permissions-rbac) and [§6](#6-messaging-administration). |
| `401` / `403` from the API | Not signed in / role lacks the permission | See the rule table in [Security & Operations §2.2](SECURITY_AND_OPERATIONS.md#22-permissions-per-area). |
| "Too many failed sign-ins" | Login lockout (§4.1) | Wait for the window, or sign in with an OTP / reset the password. |
| Public map shows only base maps | Layers not published (fresh install) | Administration › GIS layers › **Publish all** (§3.4). |
| MCP client gets `401` | No / wrong token | Send `Authorization: Bearer <PORTAL_MCP_TOKEN>` (§4.9). |
| No demo sign-in buttons | `PORTAL_ENV=production` or `PORTAL_SEED_DEMO=0` | Expected; use real accounts. |
| A capability returns `requires_optional_dependency` | Missing optional package | Install the named package or accept the fallback. |
| OTP emails not delivered | Outbox is simulated | Connect a real provider in the auth outbox seam. |
| Attachment link expired | TTL elapsed (by design) | Reopen the message for a fresh signed link. |

---

## 12. Testing a deployment

Before promoting an environment, run the automated suites (they exercise MCP, REST,
messaging and the agentic flows):

```powershell
cd backend
uv run python test_integration.py     # in-process MCP + REST assertions
uv run python smoke_http.py           # live HTTP smoke on :8011
```

See the [Testing Guide](TESTING_GUIDE.md) for coverage, expected output and how to extend
the suites — including dedicated recipes for testing the MCP surface, the API, the
messaging flow and the AI-agentic flows.
