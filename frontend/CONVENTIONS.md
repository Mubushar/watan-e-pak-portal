# Frontend conventions

How pages in `src/pages/**` are built. Read this before adding a screen.

## Stack

React 18 + TypeScript + Vite, Tailwind CSS 3, React Router 6, TanStack Query 5,
Framer Motion, Recharts, Leaflet / react-leaflet 4, Embla carousel, lucide-react icons,
zustand (state), sonner (toasts). Path alias `@/` → `src/`.

## Talking to the backend

All calls go through `src/lib/api.ts` (base `/api`, proxied by Vite to FastAPI on :8000).

```ts
import { get, post, put, del, apiUrl, wsUrl } from "@/lib/api";
import { useApi, useMutate } from "@/hooks/useApi";

const q = useApi<{ leads: Lead[] }>("/crm/leads");                // GET + cache
const q2 = useApi("/portal/market-trends", { city: "Lahore" });    // query params
const m = useMutate((b: NewLead) => post("/crm/leads", b), {
  invalidate: ["/crm"], success: "Lead added",
});
m.mutate(body);
<iframe src={apiUrl("/gis/report/property/" + id)} />              // HTML routes
```

* Pass `null` as the path to `useApi` to disable a query until its inputs exist.
* Backend ids (UUIDs) change on every backend restart — **never hard-code ids**; always
  look them up from a list endpoint.
* Errors surface as `ApiError` with the FastAPI `detail` message; `useMutate` toasts them.
* When the backend is down, GETs fall back to `src/seed/snapshot.json` (`npm run snapshot`).
* The signed-in user: `const user = useAuth((s) => s.user)` (`user.id` is also the
  messaging user id). `useAuth.getState().can("crm.manage")` checks permissions.

Explore the live API with `curl http://127.0.0.1:8000/<path>` or `http://127.0.0.1:8000/docs`;
the route list is in `docs/reference/REST_ENDPOINTS.md`.

## UI kit — `@/components/ui`

| Component | Use |
| --- | --- |
| `Button` / `ButtonLink` | `variant`: primary · gold · outline · ghost · soft · danger; `size`: sm · md · lg · icon; `loading`, `icon` |
| `Badge`, `StatusBadge`, `toneFor` | Coloured pills; `StatusBadge status="overdue"` picks a tone automatically |
| `Card`, `CardHeader`, `CardBody` | Surfaces. `CardHeader` takes `title`, `subtitle`, `icon`, `action` |
| `PageHeader` | Page title block (`crumbs`, `eyebrow`, `actions`); pass `image` for a full-bleed hero |
| `Section` | Public-page section with eyebrow/title/subtitle/action |
| `StatCard` | KPI tile (`label`, `value`, `icon`, `delta`, `hint`, `tone`) |
| `QueryState` | `<QueryState q={q}>{(data) => …}</QueryState>` — loading / error / data |
| `EmptyState`, `ErrorState`, `Skeleton`, `Spinner` | States |
| `DataTable` | Sortable, searchable, paged table (`rows`, `columns`, `search`, `onRowClick`) |
| `Tabs`, `Segmented` | Animated tabs / pill switch (controlled) |
| `Modal`, `Drawer` | Overlays |
| `Field`, `Input`, `Select`, `Textarea`, `Slider`, `RangeSlider`, `Toggle` | Forms (`Input` takes `icon`) |
| `Carousel` | Embla slider (`slideClass`, `autoplay`, `arrows`, `dots`) |
| `AreaTrend`, `LineTrend`, `Bars`, `Donut`, `Legendish`, `PALETTE` | Recharts wrappers in brand colours |
| `BarList`, `KeyValue`, `JsonView`, `CopyButton`, `ScoreRing`, `Progress`, `Avatar` | Data display |

Shared domain components:

* `@/components/property/PropertyCard` — `PropertyCard`, `PropertyRow`, `FavoriteButton`, `CompareButton`
* `@/components/map/PortalMap` — `PortalMap` (base-map switcher), `pin(kind)`, `PIN_STYLES`, `BASE_MAPS`
* `@/components/ads/AdSlot` — `<AdSlot slot="banner|sidebar|infeed|footer|hero|newsletter" />`
* `@/components/ai/ChatPanel` — the RAG assistant (`initial` prompt prop)
* `@/components/ai/Markdown` — render assistant/LLM text

Helpers: `@/lib/format` (`pkrShort` → "4.5 Crore", `pkr`, `pct`, `compact`, `num`, `area`,
`titleCase`, `date`, `timeAgo`, `initials`), `@/lib/images` (`coverImage`, `gallery`,
`cityImage`, `themedImage`, `HERO`, `BRAND`), `@/lib/utils` (`cn`, `tryJson`, `downloadText`),
`@/lib/mcp` (MCP JSON-RPC client).

## Look & feel

* Brand: deep green `brand-*` + gold `gold-*` (`bg-brand-gradient`, `bg-gold-gradient`,
  `text-gradient`, `shadow-soft`, `shadow-glow`, `glass`). Fonts: Outfit (display), Plus
  Jakarta Sans (body).
* Every screen must work in **dark mode** (`dark:` variants) and **RTL/Urdu** (use
  `ms-/me-/ps-/pe-/start-/end-` instead of `ml-/mr-/left-/right-`).
* Public pages: `<div className="container py-8">…</div>` or `PageHeader image=…` hero.
  Dashboard pages render inside the sidebar shell — start with `<PageHeader … />`.
* Use `motion` from framer-motion for entrance animations; keep it subtle.
* Responsive down to 360px.
