# Arz-e-Pak — Web Frontend

A modern, AI-first web portal for the Arz-e-Pak real-estate backend (FastAPI + MCP).
React 18 · TypeScript · Vite · Tailwind CSS · TanStack Query · Framer Motion · Leaflet ·
Recharts · Embla carousel.

## Quick start

```powershell
# 1. backend (from the repo root)
cd backend
uv run python main.py            # http://127.0.0.1:8000

# 2. frontend
cd frontend
npm install
npm run dev                      # http://localhost:5173
```

In development, sign in with a seeded demo account — the login page has one-click buttons
(`admin@portal.pk` / `Admin@12345`, agent, finance, developer, investor, buyer, …). The
buttons come from `GET /auth/config` (`demo_accounts`), which is empty in production, so a
production build shows none. Signing up as an agent or developer explains that an
administrator approves that role.

Vite proxies `/api/*` (including WebSockets), `/media/*` (uploaded listing photos) and
`/ads.txt` to the backend, so the portal is same-origin in development. Point it elsewhere with `VITE_API_TARGET` (see
`.env.example`).

| Script | What it does |
| --- | --- |
| `npm run dev` | Dev server with hot reload |
| `npm run build` | Type-check and build to `dist/` |
| `npm run preview` | Serve the production build (same proxy) |
| `npm run typecheck` | TypeScript only |
| `npm run seed` | Regenerate the local image library in `public/` |
| `npm run snapshot` | Re-capture `src/seed/snapshot.json` from a running backend |

## Seeded test assets

* **Images** — `npm run seed` (`scripts/seed-images.mjs`) generates deterministic SVG
  illustrations for every listing category (houses, villas, apartments, towers, offices,
  plazas, plots, farmhouses …) in four times of day, plus interiors, floor plans and city
  skylines, and crops photographic hero images and the logo from the brand PNGs in the repo
  root. `src/lib/images.ts` maps each backend entity to a stable image set.
* **Data** — `npm run snapshot` stores ~90 read-only API responses. When the backend is
  unreachable, GET requests transparently fall back to this snapshot and a banner says so.
  Set `VITE_FORCE_SEED=1` to always use it (design reviews without a backend).

## What’s inside

| Area | Routes | Backend wings |
| --- | --- | --- |
| Portal | `/`, `/properties`, `/properties/:id`, `/compare`, `/favorites` | properties, search (incl. `near`, `near_place`, `feature`), places (`/properties/{id}/nearby`), masterplans, intelligence, broker, finance |
| GIS & market | `/map`, `/schemes`, `/cities/:city`, `/projects`, `/insights`, `/news` | gis, gis-analysis, poi, aoi, routing, hierarchy, areas (`/areas/profile`), masterplans (DHA plan tiles + search), big-projects, news, portal |
| AI | `/ai`, `/ai/agents/:key`, `/ai/mcp` | agents (Agentic OS), `/v1` OpenAI facade, `/ai/capabilities` + `/ai/tools` (tool-calling chat), `/rag`, **MCP** (`/mcp`) |
| Tools | `/tools`, `/tools/:key` | tools (calculators, converters, calendar, GIS, CAD) |
| Content | `/pages/:key`, `/stories`, `/pricing` | content, commercial |
| Auth | `/login`, `/signup`, `/forgot` | auth (password + OTP) |
| Dashboard | `/app/*` — overview, Agentic OS, CRM, transactions, leasing, marketing, accounting, advertising, PMO, construction, maintenance, messages, profile, my listings, new listing | `/me/listings` (+ photo upload), crm, transactions, leasing, marketing, accounting, ads, pmo, construction, maintenance, messaging (+ WebSocket) |
| Administration | `/app/admin` (users & roles), `/app/admin/base-data`, `/app/admin/properties` (property database), `/app/admin/gis-layers` | roles, `/admin/basedata/*`, `/admin/properties*` (CSV export / import), `/gis/layers*` (upload, publish) |

Cross-cutting features: live market + news ticker, rotating advertisement slots
(`/ads/{id}/event` view/click billing for flat / CPM / CPC campaigns, AdSense for unsold
slots when configured), floating AI assistant (with OpenAI connected it searches and acts
through the backend's tools; otherwise a RAG chat with listing cards and agent hand-off), ⌘K federated search, natural-language property search, favourites and
side-by-side comparison, dark mode, English/Urdu (RTL), responsive down to 360 px.

**The assistant** gets its system prompt, knowledge hits and the user's memory from one
`POST /ai/context` call per question, saves replies with `POST /ai/turn`, runs independent
tool calls in parallel, and shows a **Sources** list under answers with a trust badge per
source (Official, Verified, Reference, Listing, Unverified). Its `remember` tool writes to
`/me/memory` for signed-in users.

**Map layers** come from the backend's layer records: the map shows only layers an admin
has published (`GET /gis/layers`), and the overlay endpoints return empty results with
`unpublished: true` until then. Admins publish them under Administration › GIS layers.

## Permissions and security

* Routes and menu items check the user's permissions (`RequirePermission`,
  `DashboardLayout`): CRM, transactions and marketing need `crm.view`, accounting
  `accounting.view`, PMO `projects.view`, advertising `ads.view`, Users & roles `users.view`
  or `settings.manage`, Base data `basedata.manage`, the property database
  `properties.manage`, GIS layers `gis.manage`. The server enforces the same rules; the UI
  only hides what would fail.
* The MCP console and tool runner (`/ai/mcp`) are for administrators only. Guests don't call
  protected endpoints (agent runs, saved projects, CRM smart actions, P&L, PMO).
* React Query doesn't retry `401` / `403`. An expired session signs the user out and shows a
  **Sign in** prompt.
* Markdown and news links are limited to `http(s)`, `mailto`, `tel` and relative URLs, and
  map tooltips, labels and popups escape their data (`escapeHtml` / `safeHref` in
  `src/lib/utils.ts`). Use them for any new HTML string or link built from data.

## Project layout

```
src/
  lib/          api client (+ offline snapshot), MCP client, formatting, images, i18n
  store/        zustand stores: auth session, preferences (theme, language, shortlist)
  hooks/        useApi / useMutate (React Query)
  components/
    ui/         design system (buttons, cards, tables, charts, carousel, modals, forms…)
    layout/     public + dashboard shells, command palette, error boundary
    ai/ ads/ map/ property/ ticker/   shared domain components
    agents/ biz/ collab/ gis/ tools/  page-specific components
  pages/        one file per route (lazy-loaded)
  seed/         snapshot.json (offline data)
scripts/        seed-images.mjs, snapshot-seed.mjs
```

See [CONVENTIONS.md](CONVENTIONS.md) for how to add a page.
