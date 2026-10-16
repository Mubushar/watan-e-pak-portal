# Arz-e-Pak Portal — Messaging & Notifications Guide

This guide describes the portal's **in-house team messaging system** end to end. It is
written for everyone who uses, operates or integrates the messaging wing: staff, admins
and developers. The implementation lives in `backend/messaging.py` (framework-free,
reused by both MCP and REST); the real-time feed rides an in-process pub/sub broker and the
REST layer adds `POST /messaging/...` routes and the `WS /ws/messaging/{id}` socket.

---

## 1. Purpose & principles

The internal workspace is the **primary store of record** for business conversations;
**e-mail and Telegram are complementary notification channels, never the primary**.
Concretely:

1. **Keep conversations and records inside Arz-e-Pak.** Every discussion is tied to the
   property, plan, customer or task it concerns.
2. **E-mail for formal communication; Telegram for optional alerts / quick coordination.**
3. **Files are shared as secure references, not embedded bytes** — via signed, expiring,
   permission-checked links.
4. **Messages are actionable** — any message can become a tracked task/approval/
   verification/request with an owner and deadline.
5. **Governance first** — roles, access revocation, an audit trail, and a retention/deletion
   policy are built in.
6. **Optional alerts link back to the authenticated portal** — a Telegram or e-mail alert
   carries short text and a deep link, **never confidential document content**.

---

## 2. Concepts & data model

| Concept | What it is |
| --- | --- |
| **Profile** | A messaging identity for a portal user (presence, preferences). |
| **Conversation** | `direct`, `group`, `channel` or `property`; has status `active`/`archived`/`locked`. |
| **Membership** | Links a user to a conversation with a role (`owner`/`admin`/`member`/`guest`) and read state. |
| **Message** | A post in a conversation: `text`/`system`/`attachment`/`action`/`property_link`; per-conversation monotonic `seq`; supports threads, mentions, attachments, reactions, soft delete. |
| **Attachment** | A *reference* to a file (controlled `storage_key` or `source_url`), with kind, size cap and sensitivity. |
| **Message action** | A tracked to-do from a message: kind `task`/`approval`/`verification`/`request`, owner, deadline, status `open`/`in_progress`/`done`/`cancelled`. |
| **Notification** | A queued record with a category and delivery state (`queued`/`sent`/`read`/`failed`/`deferred`). |
| **Outbox item** | A rendered per-channel payload (`in_app`/`email`/`telegram`) produced by the dispatcher. |
| **Telegram link** | A user's opt-in binding to a Telegram chat id plus allowed categories. |
| **Audit event** | An immutable record of access, file, moderation and retention actions. |
| **Message report** | A user report with a reason and a moderation outcome. |

Conversation kinds, statuses, roles, categories, attachment rules and limits are listed in
the generated [reference/MESSAGING.md](reference/MESSAGING.md).

---

## 3. Conversations

### 3.1 The default team channels

The workspace ships with the channels named in the brief — **Sales**, **Property
Verification**, **GIS & Mapping**, **Customer Support**, **Announcements** and a
**restricted Management** channel. Staff whose role is an admin role may read any
non-restricted channel without joining; the restricted Management channel is limited to
admin roles.

| Action | MCP | REST |
| --- | --- | --- |
| List channels / one channel | `msg_channels` | `GET /messaging/channels`, `GET /messaging/channels/{key}` |
| Create a channel | `msg_create_conversation` | `POST /messaging/conversations` |
| List a user's conversations | `msg_conversations` | `GET /messaging/conversations?user_id=…` |
| Open a conversation | `msg_conversation` | `GET /messaging/conversations/{id}` |
| What it's tied to | `msg_conversation_context` | `GET /messaging/conversations/{id}/context` |
| Archive / restore | `msg_archive_conversation` | `POST /messaging/conversations/{id}/archive` |

### 3.2 Direct messages, groups and property threads

* **Direct message** — `msg_direct` / `POST /messaging/direct` opens (or reuses) a 1-to-1
  conversation between two users.
* **Group** — create with `kind="group"` and a participant list.
* **Property thread** — `msg_property_thread` / `POST /messaging/property-thread` gives a
  property record its own discussion panel; the property id is validated against the
  catalogue first.

```powershell
curl -X POST "http://127.0.0.1:8000/messaging/direct" -H "Content-Type: application/json" `
  -d '{"user_a":"USR-0001","user_b":"USR-0003"}'
curl -X POST "http://127.0.0.1:8000/messaging/property-thread" -H "Content-Type: application/json" `
  -d '{"property_id":"PROP-0001","created_by":"USR-0001"}'
```

### 3.3 Membership & roles

Membership roles are `owner`, `admin`, `member`, `guest`. Members are resolved from raw
user ids **or** `@handle`s.

| Action | MCP | REST |
| --- | --- | --- |
| List members | `msg_members` | `GET /messaging/conversations/{id}/members` |
| Add / re-role | `msg_add_member` | `POST /messaging/conversations/{id}/members` |
| Update role / mute / notification level | `msg_update_member` | `PUT /messaging/conversations/{id}/members/{member_id}` |
| Remove (audited) | `msg_remove_member` | `DELETE /messaging/conversations/{id}/members/{member_id}` |

---

## 4. Messages

Posting, replies, mentions, pins, reactions, edits, deletes, search, unread counts and
read receipts are all supported.

| Action | MCP | REST |
| --- | --- | --- |
| Post | `msg_post` | `POST /messaging/conversations/{id}/messages` |
| Page messages / a thread | `msg_messages`, `msg_thread` | `GET …/messages`, `GET …/messages?thread_id=…` |
| Fetch one | `msg_message` | `GET /messaging/messages/{id}` |
| Edit (author, 15-min window) | `msg_edit_message` | `PUT /messaging/messages/{id}` |
| Delete (soft) | `msg_delete_message` | `DELETE /messaging/messages/{id}` |
| Pin | `msg_pin_message` | `POST /messaging/messages/{id}/pin` |
| React | `msg_react` | `POST /messaging/messages/{id}/react` |
| Thread view | `msg_thread` | `GET /messaging/messages/{id}/thread` |
| Search (all accessible conversations) | `msg_search` | `GET /messaging/search?q=…` |
| Mark read up to a seq | `msg_mark_read` | `POST /messaging/conversations/{id}/read` |
| Unread totals | `msg_unread`, `msg_unread_summary` | `GET /messaging/unread/{user_id}`, `…/unread-summary/{user_id}` |
| Read receipts | `msg_read_receipts` | `GET /messaging/messages/{id}/receipts` |

**Behaviour notes**

* Each conversation has a **monotonic sequence** number per message.
* **Mentions** are re-derived from the body on every edit (so adding/removing `@name`
  updates who is notified).
* **Edits** are limited to the author within a **15-minute window**; deletes are **soft**
  (tombstoned) so the audit trail is preserved.
* **Read receipts** are derived from each membership's `last_read_seq` and can be disabled
  by preference.

```powershell
curl -X POST "http://127.0.0.1:8000/messaging/conversations/CNV-0001/messages" `
  -H "Content-Type: application/json" `
  -d '{"author_id":"USR-0001","body":"Please confirm the DHA rate list","mentions":["USR-0003"]}'
curl "http://127.0.0.1:8000/messaging/search?user_id=USR-0001&q=rate%20list"
```

---

## 5. Secure file sharing

An attachment is always a **reference**: a controlled `storage_key`, or a `source_url`
pointing at an existing portal record. **File bytes never travel in the message body, the
database, or a Telegram/e-mail alert.**

* Each attachment carries a **kind** (`pdf`, `image`, `cad`, `spreadsheet`, `document`,
  `map`, `video`, `archive`, `other`), a size cap (25 MB default) and a **sensitivity**
  (`normal` / `confidential` / `restricted`). CAD, PDF, spreadsheet, map and archive kinds
  default to *confidential*; `restricted` is owner/admin only.
* Downloads are handed out through **HMAC-signed, expiring links** (default TTL **30
  minutes**). A link is minted **only after** a membership **and** role/sensitivity check,
  and is **re-verified** (signature, expiry, access) on download.

| Action | MCP | REST |
| --- | --- | --- |
| Register a reference | `msg_attach` | `POST /messaging/conversations/{id}/attachments` |
| List a conversation's files | `msg_attachments` | `GET /messaging/conversations/{id}/attachments` |
| Mint a signed link | `msg_attachment_link` | `GET /messaging/attachments/{id}/link` |
| Resolve (download) a link | `msg_attachment_resolve` | `GET /messaging/attachments/resolve/{token}` |

> **Expired link?** That is by design. Reopen the message to mint a fresh link; links are
> never permanent.

---

## 6. Actionable messages

Any message (or a whole conversation) can be turned into a **tracked action** with an
owner, a deadline, an overdue flag, a status lifecycle (`open → in_progress → done`, or
`cancelled`) and an update log.

| Kind | Use for |
| --- | --- |
| `task` | General work assignment. |
| `approval` | A decision someone must sign off. |
| `verification` | Title/document/site verification. |
| `request` | A request for information or a document. |

`msg_create_action(create_crm_task=true)` also **mirrors the action into the portal's CRM
task list**, so messaging work shows up in the broker's pipeline.

| Action | MCP | REST |
| --- | --- | --- |
| Create from a message/conversation | `msg_create_action` | `POST /messaging/conversations/{id}/actions` |
| List / fetch | `msg_actions`, `msg_action` | `GET /messaging/actions`, `GET /messaging/actions/{id}` |
| Update | `msg_update_action` | `PUT /messaging/actions/{id}` |
| Complete | `msg_complete_action` | `POST /messaging/actions/{id}/complete` |
| Auto-extract action items | `msg_action_items` | `POST /messaging/conversations/{id}/action-items` |

```powershell
curl -X POST "http://127.0.0.1:8000/messaging/conversations/CNV-0001/actions" `
  -H "Content-Type: application/json" `
  -d '{"created_by":"USR-0001","title":"Verify title deed","kind":"verification","owner_id":"USR-0003","due_on":"2026-07-05","create_crm_task":true}'
```

---

## 7. Notification queue & preferences

Notifications flow **queue → dispatcher → outbox**:

1. An event (mention, direct message, channel message, property discussion, new lead,
   approval, task update, system notice) creates a **notification** in the queue with a
   **category**.
2. Per-user, **per-category preferences** decide which channels are used (`in_app`,
   `email`, `telegram`).
3. **Quiet hours** (default 21:00–08:00) **defer** non-urgent notifications; **urgent
   categories are exempt**.
4. `msg_dispatch` (**`POST /messaging/dispatch`**) renders the per-channel payloads,
   marks each notification `sent` / `deferred` / `failed`, and writes **outbox items**.
5. A **digest** preference batches lower-priority items (default digest hour 09:00).

In production, **the same queue is drained by a background worker** that hands e-mail and
Telegram payloads to a provider — that is the documented seam. In-process, `msg_dispatch`
does it so the whole flow is demonstrable.

| Category | Default channels | Urgent |
| --- | --- | --- |
| `mention` | in-app, e-mail, Telegram | yes |
| `direct` | in-app, e-mail, Telegram | yes |
| `channel` | in-app | no |
| `property` | in-app, e-mail | no |
| `lead` | in-app, e-mail, Telegram | yes |
| `approval` | in-app, e-mail, Telegram | yes |
| `task` | in-app, e-mail | no |
| `system` | in-app | no |

| Action | MCP | REST |
| --- | --- | --- |
| A user's notifications | `msg_notifications` | `GET /messaging/notifications/{user_id}` |
| Read one / read all | `msg_read_notification`, `msg_mark_all_notifications_read` | `POST /messaging/notifications/{id}/read`, `…/{user_id}/read-all` |
| Preferences | `msg_preferences`, `msg_set_preferences` | `GET / PUT /messaging/preferences/{user_id}` |
| Drain the queue | `msg_dispatch` | `POST /messaging/dispatch` |
| The outbox | `msg_outbox` | `GET /messaging/outbox` |

```powershell
curl "http://127.0.0.1:8000/messaging/notifications/USR-0001"
curl -X POST "http://127.0.0.1:8000/messaging/dispatch" -H "Content-Type: application/json" -d '{"force":true}'
curl "http://127.0.0.1:8000/messaging/outbox"
```

---

## 8. E-mail

E-mail is the **formal** complementary channel. Configured under `messaging.email`:

| Setting | Value |
| --- | --- |
| `from` | `no-reply@arzepak.pk` |
| `reply_to` | `support@arzepak.pk` |
| `digest` | `instant` (also `hourly`, `daily`) |
| `subject_prefix` | `[Arz-e-Pak]` |

Every e-mail payload carries **short text plus an authenticated deep link**
(`/messaging/portal`) back into the portal — **never document content**. Delivery is
performed by the dispatcher (dev) or a provider-backed worker (production).

---

## 9. Telegram (optional, opt-in)

Telegram is a **complementary alert channel**, never the workspace. Users opt in
individually.

### 9.1 Linking

1. Mint a **single-use code**: `msg_telegram_link_code` (REST
   `POST /messaging/telegram/link-code`). The code is valid for **15 minutes**.
2. The user sends `/start <code>` to the bot (`telegram.bot_name` = `ArzPakPortalBot`).
3. `msg_telegram_update` (REST `POST /messaging/telegram/update`) processes the inbound
   update and binds the chat id with the user's allowed categories.

### 9.2 Bot commands

| Command | Effect |
| --- | --- |
| `/start <code>` | Link this chat to the portal account. |
| `/stop` | Unlink / opt out. |
| `/mute` | Silence alerts temporarily. |
| `/unmute` | Resume alerts. |
| `/digest` | Switch to digest delivery. |
| `/status` | Show the current link status and categories. |

### 9.3 Safety

* `telegram.attach_allowed` = **false** — documents are **never** pushed through Telegram.
* `telegram.max_text` = **320** chars; payloads are **sanitised** (stripped/truncated).
* Every alert links back to the **authenticated portal** (`/messaging/portal`); **no
  confidential data** is sent via Telegram.

| Action | MCP | REST |
| --- | --- | --- |
| Mint a link code | `msg_telegram_link_code` | `POST /messaging/telegram/link-code` |
| Link / unlink | `msg_telegram_link`, `msg_telegram_unlink` | `POST /messaging/telegram/link`, `…/unlink` |
| Status / list | `msg_telegram_status`, `msg_telegram_links` | `GET /messaging/telegram/status/{user_id}`, `…/links` |
| Process an update | `msg_telegram_update` | `POST /messaging/telegram/update` |
| Send a sanitised alert | `msg_telegram_alert` | `POST /messaging/telegram/alert` |

---

## 10. Real-time WebSockets

The messaging wing pushes events in real time over a per-conversation socket:

```
WS /ws/messaging/{conversation_id}?user_id=<user_id>
```

* **Access is re-checked on connect.** A client without access is closed with code
  **`4403`**.
* `user_id` is required — there is no ambient HTTP session.
* Events cover new messages, edits, reactions, read receipts and action changes.
* The broker is a **stdlib in-process pub/sub registry** (no `asyncio` coupling in the
  domain module); the FastAPI handler uses a pump task plus a receive loop so a client
  **disconnect is detected** without leaking resources.

**Reconnect handling:** treat the socket as best-effort — on close, reconnect with
exponential backoff, then **resynchronise** by paging `GET …/messages` from the last
`seq` you have. Delivery of a message is confirmed by its persisted `seq`; there is no
silent loss.

---

## 11. Governance

### 11.1 Moderation

Users can **report** a message with a reason (`spam`, `abuse`, `confidential_leak`,
`off_topic`, `other`). Moderators work a queue with actions `dismiss`, `delete_message`,
`mute_author`, `escalate`.

| Action | MCP | REST |
| --- | --- | --- |
| Report a message | `msg_report_message` | `POST /messaging/reports` |
| The report queue | `msg_reports` | `GET /messaging/reports` |
| Moderate | `msg_moderate_report` | `POST /messaging/reports/{id}/moderate` |

### 11.2 Audit trail

Every important action — access changes, file links, moderation, retention — is recorded.
Read it with `msg_audit` / `GET /messaging/audit` or the `messaging://audit` resource.

### 11.3 Access revocation for departing staff

`msg_revoke_access` (REST `POST /messaging/revoke-access`) removes a user from **every**
conversation and **unlinks** their Telegram. Combined with **suspending the portal account**
and revoking roles (see the
[Administration Guide](ADMINISTRATION_GUIDE.md#3-users-roles--permissions-rbac)), this is
the complete offboarding flow. Any outstanding signed attachment links are identity-scoped
and expire on their own.

### 11.4 Retention & deletion policy

Default retention is **1095 days (3 years)**, configurable. A **dry-run purge**
(`msg_purge_retention`, REST `POST /messaging/purge`) reports what would be deleted;
**pinned messages are exempt**. `msg_retention_report` / `GET /messaging/retention` shows
the policy and current holdings.

---

## 12. AI in messaging

The wing ships a **rules-based extractive baseline** (no heavy dependency required):

* **Summarisation** — `msg_summarize` / `GET /messaging/conversations/{id}/summary`
  extracts participants, topics, keywords and salient lines.
* **Action-item extraction** — `msg_action_items` / `POST …/action-items` finds
  imperatives, requests, assignments and questions; with `create=true` it creates the
  tracked actions (optionally mirroring them to CRM tasks).
* **Digest** — `msg_conversation_digest` / `GET …/digest` gives a windowed rolling digest.

These are deliberately transparent and dependency-free; the server may route **prose
summarisation to the LLM facade** (`/v1`) for richer output when available.

**Connecting to the Agentic OS** (see the
[Agentic AI Guide](AGENTIC_AI_GUIDE.md#13-agents-and-messaging)):

* **Lead routing** — a new lead can be scored (`agent_move_likelihood`) and routed to an
  owner, creating a tracked action.
* **Reminders** — deal/lease deadlines and Smart Actions arrive as `task` / `approval`
  notifications.
* **Escalation** — the `messaging_escalation_prompt`, `messaging_briefing_prompt` and
  `messaging_thread_digest_prompt` package the context for a model.

---

## 13. Rollout order

Implement and enable the wing in this order (each stage is useful on its own):

1. **Internal messaging** — channels, DMs, property threads, actions, in-app
   notifications.
2. **E-mail** — the formal complementary channel for mentions, leads and approvals.
3. **Telegram bot** — optional opt-in alerts with a deep link back to the portal.
4. **Workflow automation** — background dispatch, digests, retention, and agents raising
   actions automatically.

---

## 14. End-to-end recipe (PowerShell)

```powershell
$base = "http://127.0.0.1:8000"

# 1. the workspace, channels and a directory of members
curl "$base/messaging/overview"
curl "$base/messaging/channels"
curl "$base/messaging/profiles"

# 2. open a 1-to-1 conversation and post a message with a mention
curl -X POST "$base/messaging/direct" -H "Content-Type: application/json" `
  -d '{"user_a":"USR-0001","user_b":"USR-0003"}'
curl -X POST "$base/messaging/conversations/CNV-0001/messages" -H "Content-Type: application/json" `
  -d '{"author_id":"USR-0001","body":"Please confirm the DHA rate list","mentions":["USR-0003"]}'

# 3. turn it into an action that also lands in the CRM task list
curl -X POST "$base/messaging/conversations/CNV-0001/actions" -H "Content-Type: application/json" `
  -d '{"created_by":"USR-0001","title":"Confirm DHA rate list","kind":"request","owner_id":"USR-0003","due_on":"2026-07-05","create_crm_task":true}'

# 4. queue and drain notifications, then read the outbox
curl "$base/messaging/notifications/USR-0003"
curl -X POST "$base/messaging/dispatch" -H "Content-Type: application/json" -d '{"force":true}'
curl "$base/messaging/outbox"

# 5. opt into Telegram (mint a code, then simulate /start)
curl -X POST "$base/messaging/telegram/link-code" -H "Content-Type: application/json" -d '{"user_id":"USR-0003"}'
curl -X POST "$base/messaging/telegram/update" -H "Content-Type: application/json" `
  -d '{"chat_id":"90001","text":"/start CODE_FROM_PREVIOUS_STEP"}'
curl "$base/messaging/telegram/status/USR-0003"

# 6. summarise the conversation and extract action items
curl "$base/messaging/conversations/CNV-0001/summary"
curl -X POST "$base/messaging/conversations/CNV-0001/action-items" -H "Content-Type: application/json" `
  -d '{"user_id":"USR-0001","create":false}'

# 7. open the workspace page
start "$base/messaging/portal"
```

---

## 15. MCP & REST surface summary

* **MCP tools** — 66, prefix `msg_` (group `messaging`): see
  [reference/MCP_TOOLS.md](reference/MCP_TOOLS.md#messaging).
* **REST routes** — 71 under `/messaging`, plus `WS /ws/messaging/{conversation_id}`: see
  [reference/REST_ENDPOINTS.md](reference/REST_ENDPOINTS.md#messaging).
* **Resources** — `messaging://overview`, `…/channels`, `…/categories`, `…/profiles`,
  `…/outbox`, `…/audit`, `…/reports`, `…/statistics`; templates `messaging://conversation/{id}`,
  `messaging://unread/{user_id}`.
* **Prompts** — `messaging_briefing_prompt`, `messaging_thread_digest_prompt`,
  `messaging_escalation_prompt`.
* **HTML** — `msg_portal` / `GET /messaging/portal[.html]`.

---

## 16. Storage seam & production plan

For now the wing uses the portal's in-memory stores (seeded on startup). This is
deliberate: it keeps the whole platform runnable with zero infrastructure while every store
sits behind a **thin seam**. The intended production schema maps directly to the model:

* tables for **conversations**, **memberships**, **messages**, **attachments**,
  **notification records** and **outbox items** (plus Telegram links, audit events and
  reports),
* **PostgreSQL (+ PostGIS)** as the store, and
* **private object storage** (encrypted, versioned, lifecycle-managed) for the file bytes
  that attachments reference.

Running the dispatcher as a **background worker** and the WebSocket broker on a shared bus
(RabbitMQ/Redis) are the two other production swaps. The domain logic does not change — see
[Administration §5](ADMINISTRATION_GUIDE.md#5-data-storage--backups).

