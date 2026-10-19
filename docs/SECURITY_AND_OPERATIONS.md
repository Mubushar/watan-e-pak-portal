# Arz-e-Pak Portal — Security & Operations

This guide is for **whoever deploys and runs the portal**: DevOps, IT and the portal owner.
It covers the environment variables, the security model, durable storage and backups, and
the checklist for going to production. Day-to-day administration (roles, base data, the
property database, GIS layers) is in the [Administration Guide](ADMINISTRATION_GUIDE.md).

---

## 1. Environment variables

Settings are read once at start-up from the process environment and from `backend/.env`
(never committed). A real environment variable wins over the same line in `.env`. Restart
the backend after a change. Never put real secrets in documentation, tickets or the
`.env` comments.

### 1.1 Deployment and security

| Variable | Default | Purpose |
| --- | --- | --- |
| `PORTAL_ENV` | `development` | `production` (or `prod`) turns the safe defaults on: no demo accounts, no one-time codes in responses, API docs hidden, HSTS, and no CORS wildcard. |
| `PORTAL_SEED_DEMO` | on in development, off in production | Seed the 13 demo accounts (public passwords) and offer them on the login page. |
| `PORTAL_EXPOSE_DOCS` | on in development, off in production | Serve `/docs`, `/redoc` and `/openapi.json` to everyone. When off they return `404` (an administrator's bearer token still sees them). |
| `PORTAL_MCP_TOKEN` | *(empty)* | Static bearer token for MCP clients (Claude Desktop, LM Studio …) on `/mcp`. |
| `PORTAL_MCP_LOCAL` | on in development, off in production | With no `PORTAL_MCP_TOKEN`, let local MCP clients (loopback address, no browser `Origin` header) in without a token. Ignored in production. |
| `PORTAL_MCP_STATELESS` | `1` | Run the MCP HTTP transport statelessly (no `Mcp-Session-Id` needed). |
| `PORTAL_TRUST_PROXY` | `0` | `1` only behind your own reverse proxy: the client address comes from `X-Forwarded-For` (for rate limits). `AI_TRUST_PROXY=1` has the same effect. |
| `PORTAL_MAX_BODY_MB` | `30` | Largest request body accepted; larger requests get `413`. |
| `PORTAL_ALLOWED_HOSTS` | *(empty)* | Comma-separated `Host` names the API answers for, e.g. `arzepak.pk,api.arzepak.pk` (`localhost` and `127.0.0.1` are always added). Unset means any host is accepted. |
| `PORTAL_CORS_ORIGINS` | `*` in development, none in production | Comma-separated browser origins allowed to call the API (the web portal's domain, the desktop app's `app://arzepak`). `*` is ignored in production. |
| `PORTAL_HOST` / `PORTAL_PORT` | `127.0.0.1` / `8000` | Where `main.py` listens. `0.0.0.0` makes it reachable from the LAN. |

### 1.2 Sign-in and accounts

| Variable | Default | Purpose |
| --- | --- | --- |
| `PORTAL_AUTH_EXPOSE_OTP` | on in development, off in production | Return one-time codes as `dev_otp`. If unset, codes are returned only for channels with no delivery provider. Set explicitly, it wins. |
| `PORTAL_PBKDF2_ITERATIONS` | `600000` | PBKDF2-SHA256 rounds for **new** password hashes. Existing hashes keep the count they were made with. |
| `PORTAL_LOGIN_MAX_FAILURES` | `5` | Failed password sign-ins for one account within the window that lock it. |
| `PORTAL_LOGIN_LOCK_MINUTES` | `15` | The lock window, in minutes. |
| `PORTAL_OWNER_USERNAME`, `PORTAL_OWNER_PASSWORD` | *(empty)* | The owner's own super-admin account, re-applied on every start (optional `PORTAL_OWNER_EMAIL`, `PORTAL_OWNER_MOBILE`, `PORTAL_OWNER_NAME`). |

OTP delivery (`PORTAL_SMTP_*`, `PORTAL_SMS_PROVIDER`, `TWILIO_*`, `WHATSAPP_*`,
`PORTAL_SMS_WEBHOOK_*`) is described in the
[Administration Guide §4.4](ADMINISTRATION_GUIDE.md#44-delivering-otps-sms--whatsapp--e-mail).

### 1.3 Storage

| Variable | Default | Purpose |
| --- | --- | --- |
| `PORTAL_PERSIST` | `1` | `0` keeps everything in memory only (the test suite does this). |
| `DATABASE_URL` | *(empty)* | `postgresql://user:password@host:5432/db` stores the data in PostgreSQL (needs `psycopg[binary]`). |
| `PORTAL_DB_PATH` | `backend/data/portal.sqlite3` | The SQLite file used when `DATABASE_URL` is not set. |
| `PORTAL_DB_FLUSH_SECONDS` | `3` | How long after a write request the background writer waits before saving. |

### 1.4 Webhooks

| Variable | Used by |
| --- | --- |
| `PORTAL_WHATSAPP_APP_SECRET` | `POST /crm/webhooks/whatsapp`: the Meta app secret. The `X-Hub-Signature-256` header must match. |
| `PORTAL_WHATSAPP_VERIFY_TOKEN` | `GET /crm/webhooks/whatsapp`: Meta's subscription check (`hub.verify_token`). |
| `PORTAL_TELEGRAM_WEBHOOK_SECRET` | `POST /messaging/telegram/update`: the `secret_token` you gave Telegram's `setWebhook`. The `X-Telegram-Bot-Api-Secret-Token` header must match. |
| `PORTAL_CRM_WEBHOOK_SECRET` | `POST /crm/webhooks/lead`: the `X-Webhook-Secret` header must match. |

When one of these is unset, that webhook accepts unsigned requests. Set all of them before
the webhooks are reachable from the internet.

### 1.5 AI (OpenAI)

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENAI_API_KEY` | *(empty)* | Turns on OpenAI chat, voice and web look-ups. Without it the assistant runs in basic mode. |
| `OPENAI_MODEL` | `gpt-6-luna` | Chat model. The server always uses it; callers can't pick another model. |
| `AI_ALLOWED_MODELS` | *(empty)* | Comma-separated extra models a caller may name explicitly on `/v1`. |
| `OPENAI_MAX_OUTPUT_TOKENS` | `800` | Default reply cap. A client may ask for less, or for up to twice this. `0` = no cap. |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | The model every `/v1/embeddings` call uses. |
| `OPENAI_WEB_MODEL` | `OPENAI_MODEL` | Model for `/ai/web-lookup`. |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Azure OpenAI or a proxy. |
| `OPENAI_REALTIME_MODEL`, `OPENAI_TRANSCRIBE_MODEL`, `OPENAI_TTS_MODEL`, `OPENAI_VOICE`, `OPENAI_VOICE_ID` | see the [Administration Guide §4.5](ADMINISTRATION_GUIDE.md#45-ai-model-and-voice-for-the-assistant-openai) | Voice. |
| `AI_CHAT_PER_MINUTE`, `AI_VOICE_PER_MINUTE`, `AI_LIVE_PER_HOUR`, `AI_LIVE_MAX_MINUTES`, `AI_REQUIRE_SIGNIN` | `30`, `30`, `6`, `8`, `0` | Cost protection per caller (signed-in user, or IP address for guests). |
| `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` | *(empty)* | Send chat to another OpenAI-compatible server (LM Studio, Ollama) for testing. |

Maps, master plans and advertising have their own variables (`MAP_TILE_URL`,
`GEO_ONLINE_LOOKUP`, `MASTERPLANS_DIR`, `MASTERPLANS_GIS`, `ADS_*`); see the
Administration Guide §4.6–4.8.

---

## 2. Security model

### 2.1 The access guard (deny by default)

One ASGI middleware (`backend/access.py`) decides what every HTTP request needs, from its
method and path, before any route runs. It reads the bearer token, resolves the user, and
checks the rule table `_RULES`:

* Rules are checked **in order; the first match wins**. Specific rules come before the
  general ones for the same prefix (for example `POST /crm/leads` is public, and the rest
  of `/crm` needs `crm.view` / `crm.manage`).
* A rule is one of `public`, `user` (any signed-in user), a permission such as `crm.view`,
  `admin` (super_admin or admin), `mcp` or `docs`.
* A **read** (`GET`) that no rule names is public. A **write** (`POST`, `PUT`, `PATCH`,
  `DELETE`) that no rule names needs an administrator.
* `super_admin` has every permission. Anyone else needs the permission through one of their
  roles or a direct grant.

Answers: `401` (not signed in), `403` (signed in, missing permission), `413` (body over
`PORTAL_MAX_BODY_MB`), `429` (public enquiries over 20 per IP per minute).

Two extra checks run inside the guard:

* **Messaging acts as yourself.** The ids a messaging request acts as (`author_id`,
  `actor_id`, `created_by`, `uploaded_by`, `user_id` in the body, query or path) must be
  the signed-in user's, unless the caller is an administrator.
* **Agents see their own book.** A user whose only CRM role is `agent` sees only the leads,
  customers, deals and tasks assigned to their CRM agent; opening someone else's gets `403`.

Global search (`/portal/search`) leaves out the CRM, project and team-message groups for
callers without `crm.view`, `projects.view` or `audit.view`.

### 2.2 Permissions per area

| Area | Read | Write |
| --- | --- | --- |
| Sign-in, sign-up, OTP, password reset (`/auth/*`) | public | public |
| OTP list and outbox (`/auth/otps`, `/auth/notifications`) | `settings.manage` | — |
| Auth audit (`/auth/events`) / user list (`/auth/users`) | `audit.view` / `users.view` | — |
| Role catalogue (`/roles`) | public | `roles.manage` |
| Users (`/users/*`, `/roles/{name}/users`) | `users.view` | `roles.manage` |
| Own account (`/me/*`: listings, assistant memory) | signed in | signed in |
| Portal settings, storage status, MCP memory (`/portal/settings`, `/portal/storage*`, `/memory`) | `settings.manage` | `settings.manage` |
| Portal audit (`/portal/audit`) | `audit.view` | — |
| Base data (`/admin/basedata/*`; writes to `/cities`, `/schemes`, `/blocks`) | public lists; admin screen `basedata.manage` | `basedata.manage` |
| Property database (`/admin/properties*`; writes to `/properties`) | public listings; admin screen `properties.manage` | `properties.manage` |
| CRM, marketing, broker | `crm.view` | `crm.manage` |
| Public CRM doors: enquiry and viewing request (`POST /crm/leads`, `/crm/appointments`), agent card (`GET /crm/agents`), webhooks | public | public |
| Transactions | `crm.view` | `crm.manage` |
| Leasing | `crm.view` (inquiries, renewals, collection, funnel) | `listings.manage` (apply / inquiry are public) |
| Agentic OS | catalogue public; runs need sign-in; smart actions and scores `crm.view` | runs: signed in; approving a run: `crm.manage` |
| Team messaging | signed in | signed in; audit, outbox, retention, statistics `audit.view`; purge, dispatch, alerts, moderation `settings.manage` |
| Accounting | `accounting.view` | `accounting.manage`; payments and rent invoices `payments.manage` |
| Commercial | plans and pricing public; the rest `finance.view` | `finance.manage`; subscribe: signed in |
| PMO | `projects.view` | `projects.manage` |
| Maintenance | work orders and plans: signed in | `listings.manage`; report a problem: signed in |
| Construction | public | estimate calculator public; saved estimates: signed in |
| Images / big projects / content / news | public | `listings.manage` / `projects.manage` / `content.manage` / `news.manage` (contact form public) |
| Advertising | active ads and config public; the rest `ads.view` | `ads.manage`; view and click events public |
| GIS layers and master plans | public (published layers only) | `gis.manage`; analysis calls (buffers, polygon queries, route matrix) public |
| POI / AOI | public | `poi.manage` / `aoi.manage`; saving a study area needs `aoi.manage` |
| Calculators, tools, AI, OpenAI facade (`POST /tools/*`, `/intelligence/*`, `/finance/*`, `/rag/*`, `/ai/*`, `/v1/*`) | public | public, rate-limited by `ai_guard`; saved tool projects: signed in |
| Anything else | public | administrator |

The full, authoritative list is `_RULES` in `backend/access.py`.

### 2.3 Sign-in

* **Passwords** — PBKDF2-HMAC-SHA256 with a per-user salt. The salt records its round count
  (`i600000$…`), so raising `PORTAL_PBKDF2_ITERATIONS` affects new hashes only and older
  hashes (120,000 rounds) still verify.
* **Lockout** — after `PORTAL_LOGIN_MAX_FAILURES` (5) failed password sign-ins for one
  account within `PORTAL_LOGIN_LOCK_MINUTES` (15), password sign-in for that account is
  refused with `code: "locked"` until the window passes. OTP sign-in and password reset
  still work. Unknown accounts take the same time to check, so timing doesn't reveal which
  accounts exist. The counters are in memory and reset on restart.
* **Sessions** — opaque bearer tokens, valid 24 hours, kept in the database so a restart
  doesn't sign anyone out. Logout revokes the token; a password reset or suspension ends
  every session of that user; changing your password ends your other sessions. The web
  portal and the app sign out on an expired session and show a *Sign in* prompt.
* **Sign-up** — always OTP-verified. Picking `agent` or `developer` creates a plain `user`
  account with that role *requested*; an administrator grants it.
* **Demo accounts** — seeded only with `PORTAL_SEED_DEMO` (development). `/auth/config`
  lists them in `demo_accounts` only then, and the login pages show the one-click buttons
  only when that list is not empty.

### 2.4 MCP access

`/mcp` exposes every portal tool, so it needs one of:

1. `Authorization: Bearer <PORTAL_MCP_TOKEN>` (compared in constant time);
2. the bearer token of a signed-in **super_admin** or **admin** (the web portal's MCP
   console uses this);
3. in development only, with no `PORTAL_MCP_TOKEN` set and `PORTAL_MCP_LOCAL` on: a client
   on the loopback address that sends no browser `Origin` header, so a web page can't reach
   it.

Anything else gets `401` with `WWW-Authenticate: Bearer`. The stdio server
(`uv run mcp dev server.py`, or `python server.py` from a desktop client) has no guard: the
person who starts the process has full access.

Every MCP tool carries hints (`readOnlyHint`, `destructiveHint`, `idempotentHint`,
`openWorldHint`) so clients can auto-approve safe reads and ask before deletes or outbound
messages.

### 2.5 Browser and transport hardening

Every response carries `X-Content-Type-Options: nosniff`,
`Referrer-Policy: strict-origin-when-cross-origin`, `X-Frame-Options: SAMEORIGIN`,
`Permissions-Policy` (camera and payment off; geolocation and microphone for the portal
itself) and `Cross-Origin-Opener-Policy: same-origin`. HTML pages also get a
`Content-Security-Policy` (no plugins, no framing by other sites, forms post only to the
portal). Production adds `Strict-Transport-Security`.

* Responses over 1 KB are gzip-compressed.
* An unhandled error returns `500` with an `error_id` and no traceback; the log has the
  traceback under the same id.
* CORS: bearer tokens, no cookies. In production list your origins in
  `PORTAL_CORS_ORIGINS`; `*` is refused there.
* `PORTAL_ALLOWED_HOSTS` blocks requests for other host names (Host-header and DNS-rebinding
  tricks).

### 2.6 Webhooks

| Webhook | Check |
| --- | --- |
| WhatsApp (`POST /crm/webhooks/whatsapp`) | `X-Hub-Signature-256` = `sha256=` HMAC-SHA256 of the raw body with `PORTAL_WHATSAPP_APP_SECRET`, compared in constant time. A bad signature gets `401`. |
| Telegram (`POST /messaging/telegram/update`) | `X-Telegram-Bot-Api-Secret-Token` equals `PORTAL_TELEGRAM_WEBHOOK_SECRET`; otherwise `401`. |
| Lead capture (`POST /crm/webhooks/lead`) | `X-Webhook-Secret` equals `PORTAL_CRM_WEBHOOK_SECRET` (constant time); otherwise `401`. |

### 2.7 Cross-site scripting

* Server-rendered HTML (reports, charts, map popups, dashboards) escapes every data value.
  JSON inlined into a `<script>` can't close the tag.
* Links built from data only accept `http://` and `https://` URLs (no `javascript:` or
  `data:`).
* The web portal and the app render Markdown and news links only for `http(s)`, `mailto`,
  `tel` and relative URLs, and escape map tooltips, labels and popups (`escapeHtml` /
  `safeHref` in `src/lib/utils.ts`).

### 2.8 AI cost and model control

The server pays for OpenAI, so the server decides:

* `/v1/chat/completions` always uses `OPENAI_MODEL` (or one listed in `AI_ALLOWED_MODELS`),
  returns one completion, and caps the output (§1.5).
* `/v1/embeddings` always uses `OPENAI_EMBEDDING_MODEL`, with at most 256 inputs or 200,000
  characters.
* `/v1/completions` (legacy) is answered through chat completions on the server's model.
* Every endpoint that spends credit is rate-limited per caller and answers `429` with
  `Retry-After` over the limit.

### 2.9 Inputs

Map boxes and radii are checked: `NaN` and reversed boxes get `400`, buffer and circle radii
are limited to 100 km, ring analysis to 10 rings up to 100 km, and very large search areas
are capped. Property records must lie inside Pakistan and keep the city > scheme > block
chain consistent; GIS uploads are limited to 25 MB and 50,000 features.

---

## 3. Durable storage

### 3.1 How it works

The portal works on in-memory stores (`properties_db`, `leads_db`, `GIS_LAYERS` …) for speed.
`backend/storage.py` mirrors every one of them (about 80 stores) into a database:

* **Backend** — PostgreSQL when `DATABASE_URL` is set and `psycopg` is installed (rows in
  `JSONB`); otherwise SQLite at `PORTAL_DB_PATH` (default `backend/data/portal.sqlite3`,
  git-ignored). If `DATABASE_URL` points at PostgreSQL but `psycopg` is missing, the log
  says so and SQLite is used.
* **Tables** — `portal_rows(store, key, ord, data, updated_at)`, one row per item, and
  `portal_kv` for bookkeeping.
* **First run** — the sample data is seeded as usual and saved in full.
* **Every later start** — the saved rows replace the seed, so ids stay consistent across
  stores. A store added in a newer version keeps its seed until it is first saved.
* **Saving** — a few seconds (`PORTAL_DB_FLUSH_SECONDS`) after any write request, once a
  minute regardless, and at shutdown. Each save hashes every item and writes only what
  changed or was removed.
* **Not saved** — one-time codes, Telegram link codes and messaging rate counters (they
  expire within minutes). Master-plan label geometry is rebuilt from the plan files on start,
  so only the layer's settings are stored.
* **A store that fails to load** (for example after an incompatible model change) keeps its
  sample data, is reported as `frozen`, and is never written, so the saved rows stay intact
  until you fix the cause and restart.

Install the PostgreSQL driver with `uv sync --extra postgres` (or
`pip install "psycopg[binary]"`), then set:

```ini
DATABASE_URL=postgresql://arzepak:<password>@db.internal:5432/arzepak
```

Run **one** backend process. Each process keeps its own in-memory copy, so several
uvicorn workers would overwrite each other's changes.

### 3.2 Status and manual save

| Endpoint | Needs | Returns |
| --- | --- | --- |
| `GET /portal/storage` | `settings.manage` | `backend`, `location` (password hidden), `loaded_from_database`, `last_flush`, `last_error`, `frozen`, `stores`, `rows`, `rows_by_store`. With `PORTAL_PERSIST=0`: `{"enabled": false}`. |
| `POST /portal/storage/flush` | `settings.manage` | Saves every pending change now: `{"saved": true, "written": n, "removed": n}`. `409` when persistence is off. |

### 3.3 Backups and restore

* **SQLite** — call `POST /portal/storage/flush`, then copy the file with SQLite's online
  backup: `sqlite3 backend/data/portal.sqlite3 ".backup portal-YYYYMMDD.sqlite3"`. The
  database runs in WAL mode, so a plain file copy is only safe with the backend stopped
  (copy `portal.sqlite3` together with any `-wal` and `-shm` files).
* **PostgreSQL** — `pg_dump --format=custom --table=portal_rows --table=portal_kv --file=portal.dump "<DATABASE_URL>"`,
  plus your provider's daily backups and point-in-time recovery.
* **Restore** — stop the backend, put the file back (or `pg_restore` the dump), start it.
  The rows are loaded on start.
* **Back to the sample data** — stop the backend and delete the SQLite file, or empty
  `portal_rows` and `portal_kv` in PostgreSQL. The next start seeds and saves again.
* **Uploaded files** — listing photos live in `backend/media/uploads/`; back that folder up
  too. Built master-plan data (`backend/media/masterplans/`) can be rebuilt.

### 3.4 Relation to the PostgreSQL export toolkit

`migrate_to_postgres.py` ([Data Migration Guide](DATA_MIGRATION_GUIDE.md)) is a separate,
one-off tool: it exports the stores into a **relational** schema (78 typed tables, foreign
keys, optional PostGIS) for analytics, reporting or a future ORM. The running portal does
not read those tables. Durable storage uses its own two-table layout and discovers stores
with the same reflection (`db_migration.discover_tables`), so both cover the same stores.
The export CLI doesn't open durable storage, though: run on its own it exports the seed
data, not what the portal has saved. For backups use §3.3, not the export.

---

## 4. Production checklist

- [ ] `PORTAL_ENV=production`. This also switches off demo accounts, exposed OTPs, public
      API docs and local MCP access.
- [ ] Set `PORTAL_MCP_TOKEN` to a long random value if MCP clients need access, and give it
      only to those clients. Otherwise `/mcp` is for administrators only.
- [ ] Set `PORTAL_CORS_ORIGINS` to your exact origins: the web portal's domain and, for the
      desktop app, `app://arzepak`. The Android and iOS apps use native HTTP and need no
      CORS entry.
- [ ] Set `PORTAL_ALLOWED_HOSTS` to your API host names.
- [ ] Serve only through an **HTTPS reverse proxy** (nginx, Caddy, IIS, a cloud load
      balancer); never expose `main.py` / uvicorn directly. Set `PORTAL_TRUST_PROXY=1` only
      then.
- [ ] **Rotate every API key or password that was ever pasted into `backend/.env`, its
      comments, `.env.example`, a ticket or a chat** (OpenAI, Gemini, SMTP, Twilio,
      WhatsApp, Telegram). Deleting the line doesn't un-leak it.
- [ ] Set `PORTAL_OWNER_USERNAME` / `PORTAL_OWNER_PASSWORD` for your own super-admin, and
      remove or suspend any demo accounts copied from a development database.
- [ ] Set the webhook secrets (`PORTAL_WHATSAPP_APP_SECRET`,
      `PORTAL_TELEGRAM_WEBHOOK_SECRET`, `PORTAL_CRM_WEBHOOK_SECRET`) before exposing the
      webhooks.
- [ ] Use PostgreSQL (`DATABASE_URL`) with daily backups, or back up the SQLite file daily;
      test a restore.
- [ ] Run a single backend process.
- [ ] Publish the map layers you want public (Administration › GIS layers › **Publish
      all**, or one by one); on a fresh install every overlay starts unpublished.
- [ ] Set an OpenAI project budget and review the `AI_*` limits; consider
      `AI_REQUIRE_SIGNIN=1`.
- [ ] Check `GET /portal/storage` shows `last_error: null` and no `frozen` stores after the
      first start.

---

## 5. Operations

| Task | How |
| --- | --- |
| Health | `GET /health`, `GET /portal/health` |
| Is data being saved? | `GET /portal/storage` (`last_flush`, `last_error`) |
| Save now (before a backup or deploy) | `POST /portal/storage/flush` |
| Find an error a user reported | Search the log for the `error_id` they were shown |
| Who signed in, who was locked out | `GET /auth/events` (`login`, `login_failed`, `login_blocked`) |
| A user is locked out | Wait for the window, or have them sign in with an OTP or reset the password |
| Map layers missing for visitors | Administration › GIS layers: publish them |
| MCP client gets `401` | Send `Authorization: Bearer <PORTAL_MCP_TOKEN>` |

Run the automated suites before each release (see the [Testing Guide](TESTING_GUIDE.md)).
