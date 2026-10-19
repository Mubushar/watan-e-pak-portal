import { lazy, Suspense, useEffect, useRef, type ReactNode } from "react";
import { HashRouter, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { toast, Toaster } from "sonner";
import { App as CapApp } from "@capacitor/app";
import { SplashScreen } from "@capacitor/splash-screen";
import { StatusBar, Style } from "@capacitor/status-bar";
import { isNative, runtime } from "@/lib/platform";
import { ApiError, get } from "@/lib/api";
import { onSessionExpired, useAuth, type User } from "@/store/auth";
import { usePrefs } from "@/store/prefs";
import { AppShell } from "@/components/AppShell";
import { Spinner } from "@/components/ui";
import Home from "@/screens/Home";
import Welcome from "@/screens/Welcome";
import SignIn from "@/screens/SignIn";
import SignUp from "@/screens/SignUp";

const Explore = lazy(() => import("@/screens/Explore"));
const PropertyDetail = lazy(() => import("@/screens/PropertyDetail"));
const Assistant = lazy(() => import("@/screens/Assistant"));
const MyListings = lazy(() => import("@/screens/MyListings"));
const ListingForm = lazy(() => import("@/screens/ListingForm"));
const Survey = lazy(() => import("@/screens/Survey"));
const Saved = lazy(() => import("@/screens/Saved"));
const Profile = lazy(() => import("@/screens/Profile"));

/** Sign-in / permission errors won't fix themselves on a retry. */
const retry = (count: number, e: unknown) => !(e instanceof ApiError && (e.status === 401 || e.status === 403)) && count < 1;
const qc = new QueryClient({ defaultOptions: { queries: { staleTime: 60_000, retry, refetchOnWindowFocus: false } } });

/** Refresh the signed-in account on start (roles and permissions can change on the server),
 *  and tell someone whose session ended (401 or expiry) how to sign back in. */
function SessionSync() {
  const token = useAuth((s) => s.token);
  const setUser = useAuth((s) => s.setUser);
  const nav = useNavigate();
  const loc = useLocation();
  const here = useRef(loc.pathname + loc.search);
  here.current = loc.pathname + loc.search;
  useEffect(() => {
    if (!token) return;
    get<{ user?: User }>("/auth/me", undefined, { noFallback: true })
      .then((r) => r?.user && setUser(r.user))
      .catch(() => undefined); // a 401 already signed the user out
  }, [token, setUser]);
  useEffect(
    () =>
      // Screens that need an account redirect on their own (RequireAuth); elsewhere offer a sign-in.
      onSessionExpired(() =>
        toast.info("Your session has ended — please sign in again.", {
          action: { label: "Sign in", onClick: () => nav(`/signin?next=${encodeURIComponent(here.current)}`) },
        }),
      ),
    [nav],
  );
  return null;
}

/** Applies the theme (and native status-bar colours) whenever it changes. */
function ThemeSync() {
  const theme = usePrefs((s) => s.theme);
  useEffect(() => {
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      const dark = theme === "dark" || (theme === "system" && mq.matches);
      document.documentElement.classList.toggle("dark", dark);
      if (isNative) {
        void StatusBar.setStyle({ style: dark ? Style.Dark : Style.Light }).catch(() => undefined);
        if (runtime === "android") void StatusBar.setBackgroundColor({ color: dark ? "#07130d" : "#f6f8f6" }).catch(() => undefined);
      }
    };
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, [theme]);
  return null;
}

/** Android hardware back button: go back, or leave the app from the home screen. */
function NativeBridge() {
  const nav = useNavigate();
  const loc = useLocation();
  useEffect(() => {
    if (!isNative) return;
    void SplashScreen.hide().catch(() => undefined);
  }, []);
  useEffect(() => {
    if (!isNative) return;
    const h = CapApp.addListener("backButton", () => {
      if (["/", "/welcome"].includes(loc.pathname)) void CapApp.exitApp();
      else nav(-1);
    });
    return () => void h.then((x) => x.remove());
  }, [loc.pathname, nav]);
  return null;
}

/** Screens that need an account send guests to sign in, then bring them back. */
function RequireAuth({ children }: { children: ReactNode }) {
  const token = useAuth((s) => s.token);
  const loc = useLocation();
  if (!token) return <Navigate to={`/signin?next=${encodeURIComponent(loc.pathname + loc.search)}`} replace />;
  return <>{children}</>;
}

/** First launch shows the welcome screen; after that the app opens on Home. */
function FirstRun({ children }: { children: ReactNode }) {
  const onboarded = usePrefs((s) => s.onboarded);
  const token = useAuth((s) => s.token);
  if (!onboarded && !token) return <Navigate to="/welcome" replace />;
  return <>{children}</>;
}

const fallback = (
  <div className="flex h-[60vh] items-center justify-center">
    <Spinner className="h-7 w-7" />
  </div>
);

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <HashRouter>
        <ThemeSync />
        <NativeBridge />
        <SessionSync />
        <Suspense fallback={fallback}>
          <Routes>
            <Route path="/welcome" element={<Welcome />} />
            <Route path="/signin" element={<SignIn />} />
            <Route path="/signup" element={<SignUp />} />
            <Route element={<AppShell />}>
              <Route
                index
                element={
                  <FirstRun>
                    <Home />
                  </FirstRun>
                }
              />
              <Route path="/explore" element={<Explore />} />
              <Route path="/property/:id" element={<PropertyDetail />} />
              <Route path="/assistant" element={<Assistant />} />
              <Route path="/saved" element={<Saved />} />
              <Route path="/profile" element={<Profile />} />
              <Route
                path="/listings"
                element={
                  <RequireAuth>
                    <MyListings />
                  </RequireAuth>
                }
              />
              <Route
                path="/survey"
                element={
                  <RequireAuth>
                    <Survey />
                  </RequireAuth>
                }
              />
              <Route
                path="/listings/new"
                element={
                  <RequireAuth>
                    <ListingForm />
                  </RequireAuth>
                }
              />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </HashRouter>
      <Toaster position="top-center" richColors closeButton offset="calc(env(safe-area-inset-top) + 12px)" />
    </QueryClientProvider>
  );
}
