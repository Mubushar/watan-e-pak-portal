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

Sign in with a seeded demo account — the login page has one-click buttons
(`admin@portal.pk` / `Admin@12345`, agent, finance, developer, investor, buyer, …).

Vite proxies `/api/*` (including WebSockets) and `/media/*` to the backend, so the
backend needs no CORS changes. Point it elsewhere with `VITE_API_TARGET` (see
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
| Portal | `/`, `/properties`, `/properties/:id`, `/compare`, `/favorites` | properties, search, intelligence, broker, finance |
| GIS & market | `/map`, `/schemes`, `/cities/:city`, `/projects`, `/insights`, `/news` | gis, gis-analysis, poi, aoi, routing, hierarchy, big-projects, news, portal |
| AI | `/ai`, `/ai/agents/:key`, `/ai/mcp` | agents (Agentic OS), `/v1` OpenAI facade, `/rag`, **MCP** (`/mcp`) |
| Tools | `/tools`, `/tools/:key` | tools (calculators, converters, calendar, GIS, CAD) |
| Content | `/pages/:key`, `/stories`, `/pricing` | content, commercial |
| Auth | `/login`, `/signup`, `/forgot` | auth (password + OTP) |
| Dashboard | `/app/*` — overview, Agentic OS, CRM, transactions, leasing, marketing, accounting, advertising, PMO, construction, maintenance, messages, admin, profile, new listing | crm, transactions, leasing, marketing, accounting, ads, pmo, construction, maintenance, messaging (+ WebSocket), roles |

Cross-cutting features: live market + news ticker, rotating advertisement slots with
impression/click tracking, floating AI assistant (RAG chat with listing cards and agent
hand-off), ⌘K federated search, natural-language property search, favourites and
side-by-side comparison, dark mode, English/Urdu (RTL), responsive down to 360 px.

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
