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
* No external database or object store is required to run (data is seeded in memory) —
  see [§5](#5-data-storage--backups) for the production plan.

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
| **Production** | `uvicorn api:app --host 0.0.0.0 --port 8000` | Put a reverse proxy/TLS terminator in front. |

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
([§2.2](#22-runtime-settings)) and a small number of environment variables for
deployment-level concerns.

| Variable | Default | Purpose |
| --- | --- | --- |
| `PORTAL_MCP_STATELESS` | `1` (true) | `1` runs the MCP HTTP transport **statelessly** (each request independent — safe behind a load balancer). `0` keeps session state. |
| `PORTAL_AUTH_EXPOSE_OTP` | `1` (true) | **Dev convenience.** When true the plaintext OTP is retained and returned in responses / listed at `/auth/otps`. **Set to `0` in production.** |
| `PORTAL_LLM_BASE_URL` | *(empty)* | OpenAI-compatible LLM base URL for the `/v1` proxy mode (e.g. `https://api.openai.com/v1`). |
| `PORTAL_LLM_API_KEY` | *(falls back to `OPENAI_API_KEY`)* | API key for the upstream LLM. |
| `PORTAL_LLM_MODEL` | `gpt-4o-mini` | Default model advertised/used by the facade. |

```powershell
# Example: production-style session
$env:PORTAL_AUTH_EXPOSE_OTP = "0"
$env:PORTAL_MCP_STATELESS   = "1"
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
roles** and **30 fine-grained permissions** (`resource.action`).

### 3.1 Roles

`user`, `buyer`, `tenant`, `seller`, `landlord`, `investor`, `agent`, `agency_manager`,
`developer`, `valuer`, `accountant`, `finance_manager`, `content_editor`, `ad_manager`,
`customer_support`, `moderator`, `auditor`, `admin`, `super_admin`.

* Public self-registration may only pick from `SIGNUP_ROLES`: `user`, `buyer`, `tenant`,
  `seller`, `landlord`, `investor`, `agent`, `developer`. Everything else is granted by
  an administrator.
* A user may hold **several roles**; permissions are the union, plus any directly-granted
  extra permissions.

### 3.2 Permissions

`portal.view`, `portal.publish`, `listings.view`, `listings.manage`, `properties.view`,
`properties.manage`, `projects.view`, `projects.manage`, `gis.view`, `gis.manage`,
`poi.manage`, `aoi.manage`, `crm.view`, `crm.manage`, `accounting.view`, `accounting.manage`,
`finance.view`, `finance.manage`, `payments.view`, `payments.manage`, `content.view`,
`content.manage`, `ads.view`, `ads.manage`, `news.manage`, `users.view`, `users.manage`,
`roles.manage`, `settings.manage`, `audit.view`.

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
scoped to their (revoked) identity.

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
| `session_ttl_hours` | 24 | Bearer-token lifetime; refresh to extend. |
| `password_min_length` | 8 | Minimum password length. |
| `pbkdf2_iterations` | 120000 | Password hashing strength (PBKDF2). |
| `expose_otp` | true *(dev)* | Return codes as `dev_otp`. If `PORTAL_AUTH_EXPOSE_OTP` is unset, this applies only to channels with **no** delivery provider (§4.4). **Set `0` in production.** |
| `channels` | `sms`, `email` | Delivery channels for OTP. |

### 4.2 Flows

* **Signup** → OTP verify (purpose `signup`) → token.
* **Passwordless login** → `POST /auth/otp/request` (purpose `login`) → `POST /auth/otp/verify`.
* **Password login** → `POST /auth/login` (401 bad credentials, 403 unverified).
* **Refresh / logout** → `POST /auth/refresh`, `POST /auth/logout` (revokes the token).
* **Password reset** → `POST /auth/password/reset-request` → `POST /auth/password/reset`
  (revokes all sessions); signed-in change via `POST /auth/password/set`.

### 4.4 Delivering OTPs (SMS / WhatsApp / e-mail)

Out of the box **no code is sent anywhere**. Each message goes only to the in-memory
outbox (`GET /auth/notifications`, status `simulated`), the API returns the code as
`dev_otp`, and the apps show a *Test mode* hint. To deliver real codes, configure
`backend/delivery.py` through environment variables or `backend/.env` (template:
`backend/.env.example`, loaded at startup):

| Channel | Provider | Settings |
| --- | --- | --- |
| E-mail | Any SMTP server (Gmail app password, Outlook, Zoho, SendGrid/Mailgun/Brevo SMTP, cPanel) | `PORTAL_SMTP_HOST`, `PORTAL_SMTP_PORT`, `PORTAL_SMTP_USER`, `PORTAL_SMTP_PASSWORD`, `PORTAL_SMTP_FROM`, `PORTAL_SMTP_SECURITY` |
| Mobile | `PORTAL_SMS_PROVIDER=twilio` | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM` or `TWILIO_MESSAGING_SERVICE_SID` |
| Mobile | `PORTAL_SMS_PROVIDER=whatsapp` (WhatsApp Business Cloud API) | `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID`, `PORTAL_WHATSAPP_OTP_TEMPLATE` (an approved *authentication* template), `PORTAL_WHATSAPP_OTP_LANG`, `PORTAL_WHATSAPP_OTP_BUTTON` |
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

### 4.3 Audit & monitoring

* **Auth audit trail** — `GET /auth/events`.
* **Portal audit trail** — role/assignment/audit views; messaging keeps its own audit log
  (`messaging://audit`). Grant `audit.view` to auditors.
* **OTP outbox** — `GET /auth/notifications` (simulated SMS/e-mail outbox for demos).

---

## 5. Data, storage & backups

### 5.1 The storage seam — read this first

Data is held **in memory and seeded on startup** so the portal runs with zero external
infrastructure. This is deliberate, but it means:

* **All data is lost on restart** unless a persistence layer is added.
* Every store sits behind a thin seam so a **PostgreSQL + PostGIS** backend (and private
  object storage for attachments) can be dropped in without touching the domain logic.
  Messaging in particular documents its intended tables (conversations, memberships,
  messages, attachments, notification records, outbox items) for exactly this migration.

**Do not treat the in-memory lists as permanent storage.** For any real deployment, wire
the seam to a database before going live.

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
| Database backups | Daily full + point-in-time recovery once PostgreSQL is enabled. |
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
Telegram**.

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

- [ ] Set `PORTAL_AUTH_EXPOSE_OTP=0` (never expose OTPs in production).
- [ ] Change **all** seeded demo passwords and remove unused demo accounts.
- [ ] Terminate TLS at the reverse proxy; never expose `main.py` directly to the internet.
- [ ] Move storage to PostgreSQL + PostGIS and attachments to a private, encrypted bucket.
- [ ] Keep the object bucket private; audit signed-link TTLs.
- [ ] Run the notification dispatcher as a background worker with provider credentials
      injected via environment/secret store (never committed).
- [ ] Grant the principle of least privilege using roles + permissions; review `audit.view`
      holders.
- [ ] Back up the database and object store; test restores.
- [ ] Review messaging retention and moderation policy with legal/compliance.
- [ ] Restrict CORS/host settings at the proxy for the deployment domain.

---

## 11. Runbook

| Symptom | Likely cause | Action |
| --- | --- | --- |
| `ModuleNotFoundError` on start | Wrong working directory or deps not installed | Run from `backend/`; `uv sync`. |
| Port 8000 address in use | Stale process | Stop it or use another port; `smoke_http.py` uses 8011. |
| Data resets after restart | Expected — in-memory storage | Enable the DB seam ([§5](#5-data-storage--backups)). |
| A wing shows zero items in `portal_health` | Seeding failed for that wing | Check startup logs; the `_seed_*` routine for that wing. |
| User can't see a page/channel | Missing role/permission or membership | Review [§3](#3-users-roles--permissions-rbac) and [§6](#6-messaging-administration). |
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
