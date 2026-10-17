#!/usr/bin/env node
/**
 * Snapshot read-only backend responses into src/seed/snapshot.json.
 *
 *   npm run snapshot            # backend at http://127.0.0.1:8000
 *   API=http://host:port npm run snapshot
 *
 * The API client falls back to this snapshot whenever the backend is
 * unreachable, so the UI stays explorable offline (demo / design reviews).
 * Ids in the backend are regenerated on every start, so the snapshot is only
 * ever used as a whole — never mixed with live responses.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const API = process.env.API || "http://127.0.0.1:8000";

const PATHS = [
  "/health",
  "/properties",
  "/cities",
  "/schemes",
  "/blocks",
  "/hierarchy",
  "/news",
  "/news/channels",
  "/news/impact",
  "/portal/statistics",
  "/portal/availability",
  "/portal/market-trends",
  "/ads/active",
  "/ads",
  "/ads/slots",
  "/ads/categories",
  "/ads/performance",
  "/content/site",
  "/content/pages",
  "/content/stories",
  "/content/history",
  "/content/contacts",
  "/content/navigation",
  "/bigprojects",
  "/poi",
  "/poi/categories",
  "/aoi",
  "/gis/layers",
  "/gis/base-maps",
  "/agents/catalog",
  "/agents/overview",
  "/agents/products",
  "/agents/runs",
  "/agents/smart-actions",
  "/tools/catalog",
  "/tools/categories",
  "/tools/calculators",
  "/tools/area-units",
  "/crm/dashboard",
  "/crm/leads",
  "/crm/deals",
  "/crm/pipeline",
  "/crm/agents",
  "/crm/tasks",
  "/crm/customers",
  "/crm/appointments",
  "/broker/contacts",
  "/accounting/dashboard",
  "/accounting/invoices",
  "/accounting/profit-and-loss",
  "/accounting/balance-sheet",
  "/accounting/aging",
  "/accounting/rent-roll",
  "/accounting/cash-flow",
  "/accounting/trial-balance",
  "/pmo/overview",
  "/pmo/portfolio",
  "/pmo/projects",
  "/pmo/risks",
  "/pmo/alerts",
  "/pmo/resources",
  "/transactions",
  "/transactions/deadlines",
  "/leasing/units",
  "/leasing/funnel",
  "/leasing/renewals",
  "/maintenance/work-orders",
  "/maintenance/overview",
  "/marketing/funnel",
  "/marketing/channels",
  "/marketing/content",
  "/marketing/reengagement",
  "/messaging/overview",
  "/messaging/channels",
  "/messaging/profiles",
  "/messaging/statistics",
  "/construction/overview",
  "/construction/techniques",
  "/construction/materials",
  "/intelligence/investment/screen",
  "/intelligence/buyer/anomalies",
  "/commercial/plans",
  "/commercial/products",
  "/roles",
  "/roles/summary",
  "/i18n/languages",
  "/v1/models",
];

async function main() {
  const out = { generated_at: new Date().toISOString(), source: API, responses: {} };
  let ok = 0;
  for (const p of PATHS) {
    try {
      const r = await fetch(API + p, { headers: { Accept: "application/json" } });
      const ct = r.headers.get("content-type") || "";
      if (!r.ok || !ct.includes("json")) { console.warn(`skip ${p} (${r.status} ${ct})`); continue; }
      out.responses[p] = await r.json();
      ok++;
    } catch (e) {
      console.error(`Backend unreachable at ${API}: ${e.message}`);
      process.exit(1);
    }
  }
  // Conversations + messages for the seeded super admin, so the inbox renders offline.
  const prof = out.responses["/messaging/profiles"]?.profiles ?? [];
  const admin = prof.find((p) => p.role === "super_admin");
  if (admin) {
    const q = `/messaging/conversations?user_id=${admin.user_id}`;
    const conv = await (await fetch(API + q)).json();
    out.responses["/messaging/conversations"] = conv;
    out.seed_user_id = admin.user_id;
    for (const c of conv.conversations ?? []) {
      const m = await (await fetch(`${API}/messaging/conversations/${c.id}/messages?user_id=${admin.user_id}`)).json();
      out.responses[`/messaging/conversations/${c.id}/messages`] = m;
    }
  }
  // Property details keyed by id.
  for (const p of out.responses["/properties"]?.results ?? []) {
    const d = await (await fetch(`${API}/properties/${p.id}`)).json();
    out.responses[`/properties/${p.id}`] = d;
  }
  const dest = path.resolve(here, "..", "src", "seed", "snapshot.json");
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.writeFileSync(dest, JSON.stringify(out));
  console.log(`Snapshot: ${ok} endpoints + details -> ${path.relative(process.cwd(), dest)} (${(fs.statSync(dest).size / 1024).toFixed(0)} KB)`);
}

main();
