# Arz-e-Pak Portal — User Manual

This manual is for everyone who *uses* the portal day to day: brokers and agents,
property valuers, verification and GIS staff, finance and support teams, project
managers, and administrators. It explains how to sign in, what each page does, and how
to complete the most common tasks. Every screen is backed by the same engine that powers
the MCP and REST APIs, so what you see on screen is exactly what an integration or an AI
assistant gets.

---

## 1. What the portal does

| Area | What you can do |
| --- | --- |
| **Properties** | Browse listings, search and filter, open a full property record, compare properties. |
| **GIS & maps** | View every property on a map, run spatial queries, generate map reports and cost/forecast views. |
| **Tools & Utilities** | Mortgage, ROI, area-conversion, georeferencing and other calculators; CRS and CAD reference. |
| **CRM** | Track leads and contacts, work the pipeline, manage deals and tasks. |
| **Accounting & finance** | Invoices, rent roll, trial balance, chart of accounts, journal entries, ROI. |
| **Construction** | Estimates, timelines, take-off, material rates, advisory. |
| **Maintenance** | Component condition, lifecycle cost, defect triage, work orders. |
| **PMO** | Projects, phases, WBS, earned value, risks, portfolio dashboard. |
| **Messaging** | Internal channels and DMs, property discussions, actionable messages, notifications. |
| **Agentic OS** | AI agents that draft outreach, price a property, screen investments and route leads. |
| **AI assistant** | Ask about listings, areas, schemes and projects in English, Urdu or Roman Urdu; answers cite their sources and remember your preferences. |
| **Administration** | Base data, the property database, GIS map layers, users and roles (staff with the permission). |

---

## 2. Getting started

### 2.1 Sign in

1. Start the server (see the [Administration Guide](ADMINISTRATION_GUIDE.md#1-deployment) or
   run `uv run python main.py` in `backend/`).
2. Open <http://127.0.0.1:8000/docs> for the API, or the portal home page.
3. Sign in with an **e-mail/mobile + password**, or use **passwordless OTP login**.

### 2.2 Demo accounts (seeded)

In **development** the portal ships with seeded demo accounts so you can explore every
role, and the login page offers one-click buttons for the main ones. Passwords follow the
`Role@12345` pattern. A production installation (`PORTAL_ENV=production`) has no demo
accounts and the login page shows no demo buttons: sign in with the account an
administrator gave you.

| Role | E-mail | Password | Sees |
| --- | --- | --- | --- |
| Super admin | `admin@portal.pk` | `Admin@12345` | Everything, including settings and restricted channels. |
| Auditor | `auditor@portal.pk` | `Auditor@12345` | Read-only audit views. |
| Agent | `agent@portal.pk` | `Agent@12345` | CRM, properties, listings. |
| Developer | `developer@portal.pk` | `Developer@12345` | Projects and construction. |
| Finance manager | `finance@portal.pk` | `Finance@12345` | Accounting and finance. |
| Content editor | `content@portal.pk` | `Content@12345` | Portal content. |
| Ad manager | `ads@portal.pk` | `Ads@12345` | Advertising. |
| Valuer | `valuer@portal.pk` | `Valuer@12345` | Property intelligence. |
| Customer support | `support@portal.pk` | `Support@12345` | Support channel, tickets. |
| Investor | `investor@portal.pk` | `Investor@12345` | Investment screener. |
| Landlord | `landlord@portal.pk` | `Landlord@12345` | Leasing. |
| Buyer | `bilal@example.com` | `Buyer@12345` | Buyer-side search. |
| Tenant | `tenant@portal.pk` | `Tenant@12345` | Own unit / maintenance requests. |

> These passwords are public. They are never created in production — see the
> [Administration Guide](ADMINISTRATION_GUIDE.md#10-security-hardening-checklist).

### 2.3 Create your own account

Sign-up is **OTP-verified** and takes three steps:

1. **Register** — e-mail or mobile plus a password.
2. **Verify** — enter the one-time code delivered to your e-mail/mobile.
3. **Use the token** — the verification returns a session token; send it as
   `Authorization: Bearer <token>` on later requests.

In the REST API this is `POST /auth/signup` → `POST /auth/verify-otp`. In the MCP tools it
is `auth_signup` and `auth_verify_otp`. In development, when no SMS / e-mail provider is set
up, the code is shown on screen ("Test mode") instead of being sent.

* You can pick buyer, tenant, seller, landlord, investor or a plain user account yourself.
  If you sign up as an **agent** or **developer**, your account starts as a normal user and
  the role waits for an administrator's approval; you'll see a note saying so.
* After **5 wrong passwords** in 15 minutes, password sign-in for that account pauses for 15
  minutes. You can still sign in with a one-time code, or reset your password.
* A session lasts 24 hours. When it expires the portal signs you out and shows a **Sign in**
  prompt. Changing your password signs you out everywhere else.

---

## 3. Navigating the portal

The portal home page links to the public pages and the working wings:

| Page | URL | Purpose |
| --- | --- | --- |
| About / Mission / Services / Why Us / Team / Careers | `/content/pages/{about,mission,…}` | Marketing and informational pages. |
| How It Works / FAQ / Terms / Privacy | `/content/pages/{how-it-works,faq,terms,privacy}` | Help and legal. |
| Construction wing | `/construction/portal` | Construction calculators and estimates. |
| Maintenance wing | `/maintenance/portal` | Maintenance planning and triage. |
| Tools Center | `/tools/portal` | All utilities and calculators. |
| PMO dashboard | `/pmo/portal` | Projects, portfolio, earned value (needs `projects.view`). |
| Messaging workspace | `/messaging/portal` | Channels, DMs and notifications (needs sign-in). |
| Agentic OS | `/agents/portal` | The AI products and agents. |

Every HTML page accepts **`?lang=xx`** (e.g. `?lang=ur`) and **`?theme=auto|light|dark`**,
for example:

```powershell
start "http://127.0.0.1:8000/tools/portal?lang=ur&theme=dark"
```

The PMO and messaging pages (like the CRM, accounting and transactions pages) contain
staff data, so the server only serves them with a sign-in token. A browser address bar
can't send one: use the web portal's dashboard (`/app/pmo`, `/app/messages` …) after
signing in, or fetch the page with your token.

---

## 4. Working with properties

* **Browse & search** — filter by city, scheme, type, price and status. From the API:
  `GET /properties` and `GET /properties/{property_id}`.
* **Property record** — the record holds the full hierarchy (city → scheme → block →
  plot → unit), owner/tenant links, media, valuations and its own **discussion thread**
  (see [Messaging](#12-messaging--notifications)).
* **Compare** — `GET /properties/{property_id}/compare/{other_id}` puts two properties
  side by side; over MCP read the resource template `properties://compare/{property_ids}`.
* **Property intelligence** — `GET /property-intelligence/...` returns the GIS score and
  market context for an address or property.

### Common task — find a property and open its map report

```powershell
# 1. search
curl "http://127.0.0.1:8000/properties?city=lahore"
# 2. the property's GIS report (HTML)
start "http://127.0.0.1:8000/gis/report/property/PROP-0001"
```

### Common task — compare two properties

```powershell
curl "http://127.0.0.1:8000/properties/PROP-0001/compare/PROP-0002"
```

---

## 5. GIS & maps

The GIS wing turns locations into insight: master plans, boundaries, zones, buffers,
thematic maps, cost and forecast views, and exportable GeoJSON/KML.

| Task | How |
| --- | --- |
| See a property on the map | `GET /gis/map/property/{property_id}` |
| Nearby amenities within X km | `GET /gis/nearby/{latitude}/{longitude}/{radius_km}` |
| Export geometry | `GET /gis/geojson/…`, `GET /gis/kml/…` |
| Full analysis report | `GET /gis/report/{entity_type}/{entity_id}` |
| Cost / development perspective | `GET /gis/cost/{entity_type}/{entity_id}` |
| Predictions & scenarios | `GET /gis/forecast/{entity_type}/{entity_id}` |

Maps respect your **language** and **theme** and embed the portal's basemaps and layer
switch. See the GIS section of `backend/README.md` for the full layer list.

**Which layers you see depends on publishing.** Overlays such as boundaries, roads, water,
points of interest, mega projects and the DHA master plans appear on the public map only
after an administrator has **published** them (Administration › GIS layers). If the map
shows only the base map, nothing has been published yet. Published layers can be switched
on and off in the map's **Layers** panel; some are on by default.

---

## 6. Tools & Utilities

The **Tools Center** (`/tools/portal`) gathers three dozen calculators and reference
tables in six categories:

1. **Mortgage & finance** — monthly payment, affordability, amortisation, ROI.
2. **Area & units** — marla/kanal/sq-ft/sq-m conversion (both the *standard* 272.25 sq-ft
   marla and the *small* 225 sq-ft marla), all area units.
3. **Property math** — appreciation, rental yield, capital gain, stamp duty.
4. **Geodesy** — distance/bearing, georeference a scanned plan, CRS reference.
5. **Planning** — construction cost, plot coverage, feasibility.
6. **Reference** — CAD formats, CRS list, calendars (Gregorian + civil Islamic/Hijri).

Example — a mortgage calculation over REST:

```powershell
curl "http://127.0.0.1:8000/finance/mortgage?principal=8000000&rate=21&years=20"
```

Open the landing page: `start "http://127.0.0.1:8000/tools/portal"`.

---

## 7. CRM

* **Leads** — captured from enquiries, the website and messaging; each has a source,
  score and owner. `GET /crm/leads`.
* **Contacts** — buyers, sellers, landlords, tenants and professionals. `GET /crm/contacts`.
* **Pipeline & deals** — move deals through stages; commission is derived from the live
  pipeline (`GET /crm/pipeline`, `GET /broker/commission-projection`).
* **Tasks** — follow-ups with owners and due dates. `GET /crm/tasks`. Messages can
  create CRM tasks automatically (see the [Messaging Guide](MESSAGING_GUIDE.md#6-actionable-messages)).

### Common task — "who should I call next?"

```powershell
curl "http://127.0.0.1:8000/broker/contacts"     # scored contact list
```

---

## 8. Accounting & finance

* **Chart of accounts**, **journal entries**, **invoices**, **rent roll**, **trial
  balance** and an **accounting dashboard**. `GET /accounting/...`.
* **ROI** analysis and **finance** views over the same data.

Accounting is standard double-entry: journal lines are keyed `account`, and the trial
balance always balances. Use the accounting dashboard for a live snapshot.

---

## 9. Construction

Open `/construction/portal`. You can:

* Look up **techniques**, **materials** and **element rates**.
* Produce an **element-wise estimate** and a **project timeline**.
* Run a **take-off** and read real-estate **impact/advisory** notes.

```powershell
curl -X POST "http://127.0.0.1:8000/construction/estimate?covered_area=2000&technique=rcc_frame"
```

---

## 10. Maintenance

Open `/maintenance/portal`. You can:

* Inspect **components**, **services** and the **condition scale**.
* Estimate **annual operating cost** and a **reserve**.
* Triage a **defect** and generate a **work order**.

```powershell
curl "http://127.0.0.1:8000/maintenance/estimate?covered_area=2000&age_years=8"
```

---

## 11. Projects & Monitoring (PMO)

Open `/pmo/portal`. The PMO wing covers eight project types (residential, commercial,
infrastructure, …) with a six-day working week.

| Task | How |
| --- | --- |
| Portfolio dashboard | `/pmo/portal` |
| Create a project (seeds phases + WBS) | `POST /pmo/projects` |
| Critical path & earned value | `GET /pmo/projects/{project_id}/…` |
| Health (RAG) & risk register | `GET /pmo/projects/{project_id}/health` |
| Printable status report | `GET /pmo/projects/{project_id}/report` |

A project carries both a **baseline budget** and a **current/revised budget**, so schedule
(`spi`) and cost (`cpi`) performance can be tracked honestly.

---

## 12. Messaging & notifications

Open `/messaging/portal` — this is the internal communication workspace.

* **Channels** — Sales, Property Verification, GIS & Mapping, Customer Support,
  Announcements and a restricted **Management** channel.
* **Direct messages** and **group chats**.
* **Property discussions** — every property record has its own thread.
* **Threaded replies, `@mentions`, pins, reactions, edits, search, read receipts and
  unread counts.**
* **Attachments are shared as secure links** (they expire), never pasted into the body.
* **Turn any message into a task, approval, verification or request** with an owner and a
  deadline.
* **Notifications** — in-app by default; optional e-mail and Telegram, with per-category
  preferences and quiet hours.

Full detail, including Telegram setup and the end-to-end flow, is in the
[Messaging Guide](MESSAGING_GUIDE.md).

---

## 13. The Agentic OS (AI helpers)

The **Agentic OS** (`/agents/portal`) exposes 24 AI agents across 8 products. In
plain terms, they can:

* **Brief you each morning** — prioritised deals, deadlines, renewals, arrears and warm
  leads (`smart_actions`).
* **Draft outreach** and marketing content for your review.
* **Price a property** (CMA) and turn an address into a marketing kit.
* **Recommend properties** to a buyer from a natural-language brief.
* **Screen investments** and underwrite a deal.
* **Route and qualify leads**, and re-engage dormant ones.

Anything with an **approval gate** waits for a human before acting — you are always in
control. Agents first gather and analyse; anything that sends, books or changes a record
runs only after someone with CRM rights approves the run, and the approval carries their
name. Running agents needs you to be signed in. Read [AGENTIC_AI_GUIDE.md](AGENTIC_AI_GUIDE.md)
to go deeper.

---

## 14. The AI assistant

The floating assistant in the web portal (and the **Assistant** tab in the app) answers in
the language you write in: English, Urdu or Roman Urdu. Ask things like "5 marla house in
Bahria under 2 crore", "Is Blue World City approved?" or "لاہور میں 10 مرلہ گھر".

* **Sources under every answer.** When the reply uses the portal's knowledge, a
  **Sources** list appears under it: the `[1]`, `[2]` … markers in the text point to these
  entries. Each has a badge for how far to trust it — **Official** (a government body or
  development authority), **Verified** (checked by the portal), **Reference** (an
  established reference or news outlet), **Listing** (as listed by the owner or agent) or
  **Unverified** — and a link to the original where there is one. Check approval status
  with the authority before paying anything.
* **It remembers your preferences.** When you are signed in, the assistant remembers what
  helps the next search — your budget, cities and schemes, property type and size,
  bedrooms, buying or renting, reply language — and anything you ask it to remember
  ("remember that I work in Blue Area"). Follow-ups like "and in Lahore?" keep the rest of
  your search. Guests get no memory. It never stores CNIC, card or bank numbers or
  passwords, and no one else (not even an administrator) can see your memories.
* **Seeing and clearing what it remembers.** There is no screen for this yet; use the API
  with your sign-in token:

  | To | Call |
  | --- | --- |
  | See your memories | `GET /me/memory` |
  | Forget one | `DELETE /me/memory/{id}` |
  | Forget everything (including recent conversations) | `DELETE /me/memory` |
  | Switch memory off / on | `PUT /me/memory/settings` with `{"enabled": false}` / `{"enabled": true}` |

  ```powershell
  $H = @{ Authorization = "Bearer $token" }
  Invoke-RestMethod -Uri "http://127.0.0.1:8000/me/memory" -Headers $H
  Invoke-RestMethod -Method Put -Uri "http://127.0.0.1:8000/me/memory/settings" -Headers $H `
    -ContentType "application/json" -Body '{"enabled": false}'
  ```

---

## 15. Administration (staff)

Staff whose role has the permission see an **Administration** menu in the dashboard:

| Screen | For | What you do there |
| --- | --- | --- |
| **Users & roles** | administrators | Accounts, roles (including approving requested agent / developer roles), permissions. |
| **Base data** | `basedata.manage` | Cities, housing schemes / societies (with approval status and sources) and blocks. |
| **Property database** | `properties.manage` | Every listing with every field: search, filter, edit, bulk feature / status / agent / delete, CSV export and import (always checked first). |
| **GIS layers** | `gis.manage` | Upload map layers (GeoJSON, KML, GPX, CSV), edit their style, and publish them to the public map. |

Step-by-step details are in the
[Administration Guide §3.4](ADMINISTRATION_GUIDE.md#34-administration-screens-web-portal).

---

## 16. Language & theme

* Add `?lang=ur` (or another supported code) to any HTML page for Urdu.
* Add `?theme=dark` or `?theme=light`; `auto` follows the operating system.
* Your theme choice is remembered in the browser (`localStorage: portal-theme`).

---

## 17. Handy URLs

| Purpose | URL |
| --- | --- |
| Interactive API docs | `/docs` |
| ReDoc API docs | `/redoc` |
| Portal content pages | `/content/pages/{key}` |
| Tools Center | `/tools/portal` |
| PMO dashboard | `/pmo/portal` |
| Messaging workspace | `/messaging/portal` |
| MCP endpoint (Streamable HTTP) | `/mcp` |
| OpenAI-compatible facade | `/v1` |

---

## 18. Getting help

* **A page looks empty** — confirm the server is running and you are signed in; some wings
  filter by your role, and pages your role can't use are hidden from the menu.
* **"Please sign in" or "Your role doesn't include … access"** — the feature needs a
  signed-in account or a role you don't have; ask an administrator.
* **"Too many failed sign-ins"** — wait 15 minutes, or sign in with a one-time code /
  reset your password.
* **The map shows no overlays** — an administrator hasn't published the map layers yet.
* **You can't see a channel** — the **Management** channel is restricted to admin roles;
  ask an administrator to grant access.
* **A file link has expired** — attachment links are time-limited by design; open the
  message again to get a fresh link.
* **A capability says it needs an optional dependency** — that feature (e.g. PDF export
  or advanced reprojection) requires an extra package; see the
  [Administration Guide](ADMINISTRATION_GUIDE.md#9-optional-dependencies).

For operational problems, administrators should use the
[Administration Guide runbook](ADMINISTRATION_GUIDE.md#11-runbook).
