/**
 * Advertising. Slots show the portal's own sponsored ads first (sold to vendors, served
 * by the backend's /ads). When a slot has none, Google fills it where its rules allow:
 *   web build  → AdSense (not allowed inside mobile or desktop apps)
 *   Android/iOS → an AdMob banner above the tab bar
 *   desktop    → sponsored ads only
 * Ids come from GET /ads/config, so nothing is hard-coded in the app.
 */
import { AdMob, AdmobConsentStatus, BannerAdPluginEvents, BannerAdPosition, BannerAdSize } from "@capacitor-community/admob";
import { get, post } from "./api";
import { isNative, runtime } from "./platform";

export interface Ad {
  id: string;
  title: string;
  headline: string;
  body?: string | null;
  advertiser: string;
  category: string;
  slot: string;
  cta_label?: string | null;
  cta_url?: string | null;
  image_url?: string | null;
  price_text?: string | null;
  offer?: string | null;
  phone?: string | null;
  sample?: boolean;
  sponsored_label?: string;
}

export interface AdConfig {
  direct: boolean;
  sponsored_label: string;
  advertise: { title: string; body: string; email: string | null };
  adsense: { client: string; slots: Record<string, string> } | null;
  admob: { testing: boolean; banner: Partial<Record<"android" | "ios", string>> } | null;
}

let config: Promise<AdConfig | null> | null = null;
export function adConfig(): Promise<AdConfig | null> {
  config ??= get<AdConfig>("/ads/config", undefined, { noFallback: true }).catch(() => {
    config = null;
    return null;
  });
  return config;
}

// Each slot's ads, cached for a minute so moving between screens doesn't refetch.
const cache = new Map<string, { at: number; ads: Promise<Ad[]> }>();
export function adsFor(slot: string): Promise<Ad[]> {
  const hit = cache.get(slot);
  if (hit && Date.now() - hit.at < 60_000) return hit.ads;
  const ads = get<{ ads: Ad[] }>("/ads/section", { slot, limit: 6 }, { noFallback: true })
    .then((r) => r.ads ?? [])
    .catch(() => {
      cache.delete(slot);
      return [] as Ad[];
    });
  cache.set(slot, { at: Date.now(), ads });
  return ads;
}

/** Report a view or a tap (the backend counts each viewer once per window). */
export function trackAd(id: string, event: "impression" | "click"): void {
  void post(`/ads/${id}/event`, { event }, { noFallback: true }).catch(() => undefined);
}

// ------------------------------------------------------------------ AdSense (web)

declare global {
  interface Window {
    adsbygoogle?: unknown[];
  }
}

let adsenseLoaded = false;
export function loadAdSense(client: string): void {
  if (adsenseLoaded || runtime !== "web") return;
  adsenseLoaded = true;
  const s = document.createElement("script");
  s.async = true;
  s.crossOrigin = "anonymous";
  s.src = `https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=${encodeURIComponent(client)}`;
  document.head.appendChild(s);
}

// ------------------------------------------------------------------ AdMob (Android / iOS)

let admobReady: Promise<boolean> | null = null;
async function initAdMob(testing: boolean): Promise<boolean> {
  try {
    // iOS asks for tracking permission; EU/UK users get Google's consent form.
    if (runtime === "ios") {
      const t = await AdMob.trackingAuthorizationStatus();
      if (t.status === "notDetermined") await AdMob.requestTrackingAuthorization();
    }
    const consent = await AdMob.requestConsentInfo();
    if (consent.isConsentFormAvailable && consent.status === AdmobConsentStatus.REQUIRED) await AdMob.showConsentForm();
    await AdMob.initialize({ initializeForTesting: testing });
    return true;
  } catch {
    return false;
  }
}

let bannerState: "none" | "shown" | "hidden" = "none";
let sizeListener: Promise<unknown> | null = null;

/** Show the AdMob banner just above the tab bar (phones) or at the bottom (tablets). */
export async function showNativeBanner(): Promise<void> {
  if (!isNative) return;
  const cfg = await adConfig();
  const adId = cfg?.admob?.banner[runtime as "android" | "ios"];
  if (!cfg?.admob || !adId) return;
  admobReady ??= initAdMob(cfg.admob.testing);
  if (!(await admobReady)) return;
  try {
    if (bannerState === "hidden") {
      await AdMob.resumeBanner();
    } else if (bannerState === "none") {
      sizeListener ??= AdMob.addListener(BannerAdPluginEvents.SizeChanged, (s) =>
        document.documentElement.style.setProperty("--ad-banner-h", `${Math.round(s.height)}px`),
      );
      const tabBar = window.matchMedia("(min-width: 768px)").matches ? 0 : 64;
      await AdMob.showBanner({ adId, adSize: BannerAdSize.ADAPTIVE_BANNER, position: BannerAdPosition.BOTTOM_CENTER, margin: tabBar, isTesting: cfg.admob.testing });
    }
    bannerState = "shown";
  } catch {
    /* no fill / offline: the screen just has no banner */
  }
}

export async function hideNativeBanner(): Promise<void> {
  if (bannerState !== "shown") return;
  bannerState = "hidden";
  document.documentElement.style.setProperty("--ad-banner-h", "0px");
  await AdMob.hideBanner().catch(() => undefined);
}
