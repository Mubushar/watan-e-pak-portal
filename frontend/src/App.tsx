import { RequirePermission } from "@/components/layout/RequirePermission";
import { lazy, Suspense, useEffect, useRef, type ComponentType } from "react";
import { Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { onSessionExpired } from "@/store/auth";
import { PublicLayout } from "@/components/layout/PublicLayout";
import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { CommandPalette } from "@/components/layout/CommandPalette";
import { PrefsSync } from "@/components/layout/Chrome";
import { Spinner } from "@/components/ui";

/** Route-level code splitting: every page is its own chunk. */
const P: Record<string, ComponentType> = {
  // Public portal
  Home: lazy(() => import("@/pages/public/Home")),
  Properties: lazy(() => import("@/pages/public/Properties")),
  PropertyDetail: lazy(() => import("@/pages/public/PropertyDetail")),
  Compare: lazy(() => import("@/pages/public/Compare")),
  Favorites: lazy(() => import("@/pages/public/Favorites")),
  // GIS, market & content
  MapExplorer: lazy(() => import("@/pages/gis/MapExplorer")),
  Insights: lazy(() => import("@/pages/gis/Insights")),
  News: lazy(() => import("@/pages/gis/News")),
  Schemes: lazy(() => import("@/pages/gis/Schemes")),
  CityPage: lazy(() => import("@/pages/gis/CityPage")),
  Projects: lazy(() => import("@/pages/gis/Projects")),
  Infrastructure: lazy(() => import("@/pages/gis/Infrastructure")),
  ContentPage: lazy(() => import("@/pages/content/ContentPage")),
  Stories: lazy(() => import("@/pages/content/Stories")),
  PhotoCredits: lazy(() => import("@/pages/content/PhotoCredits")),
  Pricing: lazy(() => import("@/pages/content/Pricing")),
  // AI & tools
  AIHub: lazy(() => import("@/pages/ai/AIHub")),
  AgentDetail: lazy(() => import("@/pages/ai/AgentDetail")),
  McpConsole: lazy(() => import("@/pages/ai/McpConsole")),
  ToolsCenter: lazy(() => import("@/pages/tools/ToolsCenter")),
  ToolPage: lazy(() => import("@/pages/tools/ToolPage")),
  // Auth
  Login: lazy(() => import("@/pages/auth/Login")),
  Signup: lazy(() => import("@/pages/auth/Signup")),
  Forgot: lazy(() => import("@/pages/auth/Forgot")),
  // Dashboard
  Overview: lazy(() => import("@/pages/app/Overview")),
  AgentOps: lazy(() => import("@/pages/app/AgentOps")),
  Crm: lazy(() => import("@/pages/app/Crm")),
  CrmDashboard: lazy(() => import("@/pages/app/CrmDashboard")),
  BaseData: lazy(() => import("@/pages/app/BaseData")),
  GisLayersAdmin: lazy(() => import("@/pages/app/GisLayersAdmin")),
  PropertiesAdmin: lazy(() => import("@/pages/app/PropertiesAdmin")),
  Accounting: lazy(() => import("@/pages/app/Accounting")),
  Transactions: lazy(() => import("@/pages/app/Transactions")),
  Leasing: lazy(() => import("@/pages/app/Leasing")),
  Maintenance: lazy(() => import("@/pages/app/Maintenance")),
  Marketing: lazy(() => import("@/pages/app/Marketing")),
  Pmo: lazy(() => import("@/pages/app/Pmo")),
  PmoProject: lazy(() => import("@/pages/app/PmoProject")),
  Messages: lazy(() => import("@/pages/app/Messages")),
  Ads: lazy(() => import("@/pages/app/Ads")),
  Construction: lazy(() => import("@/pages/app/Construction")),
  Admin: lazy(() => import("@/pages/app/Admin")),
  Profile: lazy(() => import("@/pages/app/Profile")),
  ListingNew: lazy(() => import("@/pages/app/ListingNew")),
  MyListings: lazy(() => import("@/pages/app/MyListings")),
  NotFound: lazy(() => import("@/pages/NotFound")),
};

/** Any of these opens Administration (users, roles, settings); the API checks each call. */
const ADMIN_PERMS = ["users.view", "settings.manage"];

function Fallback() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <Spinner className="h-8 w-8" />
    </div>
  );
}

/** A session that ends on its own (401 from the API, or the token expired) leaves the user signed out:
 *  dashboard pages redirect to sign-in themselves; elsewhere a toast offers to sign back in. */
function SessionExpiryNotice() {
  const nav = useNavigate();
  const loc = useLocation();
  const here = useRef(loc.pathname + loc.search);
  here.current = loc.pathname + loc.search;
  useEffect(
    () =>
      onSessionExpired(() =>
        toast.info("Your session has ended — please sign in again.", {
          action: { label: "Sign in", onClick: () => nav(`/login?next=${encodeURIComponent(here.current)}`) },
        }),
      ),
    [nav],
  );
  return null;
}

export default function App() {
  return (
    <>
      <PrefsSync />
      <SessionExpiryNotice />
      <CommandPalette />
      <Suspense fallback={<Fallback />}>
        <Routes>
          <Route element={<PublicLayout />}>
            <Route index element={<P.Home />} />
            <Route path="properties" element={<P.Properties />} />
            <Route path="properties/:id" element={<P.PropertyDetail />} />
            <Route path="compare" element={<P.Compare />} />
            <Route path="favorites" element={<P.Favorites />} />
            <Route path="map" element={<P.MapExplorer />} />
            <Route path="insights" element={<P.Insights />} />
            <Route path="news" element={<P.News />} />
            <Route path="schemes" element={<P.Schemes />} />
            <Route path="cities/:city" element={<P.CityPage />} />
            <Route path="projects" element={<P.Projects />} />
            <Route path="infrastructure" element={<P.Infrastructure />} />
            <Route path="pages/:key" element={<P.ContentPage />} />
            <Route path="stories" element={<P.Stories />} />
            <Route path="credits" element={<P.PhotoCredits />} />
            <Route path="pricing" element={<P.Pricing />} />
            <Route path="ai" element={<P.AIHub />} />
            <Route path="ai/agents/:key" element={<P.AgentDetail />} />
            <Route path="ai/mcp" element={<P.McpConsole />} />
            <Route path="tools" element={<P.ToolsCenter />} />
            <Route path="tools/:key" element={<P.ToolPage />} />
            <Route path="login" element={<P.Login />} />
            <Route path="signup" element={<P.Signup />} />
            <Route path="forgot" element={<P.Forgot />} />
            <Route path="*" element={<P.NotFound />} />
          </Route>
          <Route path="app" element={<DashboardLayout />}>
            <Route index element={<P.Overview />} />
            <Route path="agents" element={<P.AgentOps />} />
            <Route path="crm-dashboard" element={<RequirePermission perm="crm.view" area="the CRM"><P.CrmDashboard /></RequirePermission>} />
            <Route path="crm" element={<RequirePermission perm="crm.view" area="the CRM"><P.Crm /></RequirePermission>} />
            <Route path="accounting" element={<RequirePermission perm="accounting.view" area="Accounting"><P.Accounting /></RequirePermission>} />
            <Route path="transactions" element={<RequirePermission perm="crm.view" area="Transactions"><P.Transactions /></RequirePermission>} />
            <Route path="leasing" element={<P.Leasing />} />
            <Route path="maintenance" element={<P.Maintenance />} />
            <Route path="marketing" element={<RequirePermission perm="crm.view" area="Marketing"><P.Marketing /></RequirePermission>} />
            <Route path="pmo" element={<RequirePermission perm="projects.view" area="Projects (PMO)"><P.Pmo /></RequirePermission>} />
            <Route path="pmo/:id" element={<RequirePermission perm="projects.view" area="Projects (PMO)"><P.PmoProject /></RequirePermission>} />
            <Route path="messages" element={<P.Messages />} />
            <Route path="ads" element={<RequirePermission perm="ads.view" area="Advertising"><P.Ads /></RequirePermission>} />
            <Route path="construction" element={<P.Construction />} />
            <Route path="admin" element={<RequirePermission perm={ADMIN_PERMS} area="Users & roles"><P.Admin /></RequirePermission>} />
            <Route path="admin/base-data" element={<RequirePermission perm="basedata.manage" area="base data"><P.BaseData /></RequirePermission>} />
            <Route path="admin/properties" element={<RequirePermission perm="properties.manage" area="the property database"><P.PropertiesAdmin /></RequirePermission>} />
            <Route path="admin/gis-layers" element={<RequirePermission perm="gis.manage" area="GIS layers"><P.GisLayersAdmin /></RequirePermission>} />
            <Route path="profile" element={<P.Profile />} />
            <Route path="listings" element={<P.MyListings />} />
            <Route path="listings/new" element={<P.ListingNew />} />
            <Route path="*" element={<P.NotFound />} />
          </Route>
        </Routes>
      </Suspense>
    </>
  );
}
