/**
 * Device location for surveying on site. Uses the web Geolocation API, which works in mobile
 * browsers, on PCs and inside the Android / iOS app shells (Capacitor's web view asks for the
 * permissions declared in AndroidManifest.xml / Info.plist).
 */
import type { User } from "@/store/auth";

export interface Fix {
  latitude: number;
  longitude: number;
  /** Metres (68% confidence), as reported by the device. */
  accuracy: number;
  at: number;
}

/** One high-accuracy GPS fix; waits up to `timeoutMs` for the satellites. */
export function getPosition(timeoutMs = 20_000): Promise<Fix> {
  return new Promise((resolve, reject) => {
    if (!("geolocation" in navigator)) return reject(new Error("This device can't share its location"));
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ latitude: p.coords.latitude, longitude: p.coords.longitude, accuracy: Math.round(p.coords.accuracy), at: p.timestamp }),
      (e) =>
        reject(
          new Error(
            e.code === e.PERMISSION_DENIED
              ? "Location is off for Arz-e-Pak — allow it in the device settings"
              : e.code === e.TIMEOUT
                ? "No GPS fix yet — step outside or near a window and try again"
                : "Couldn't read the location",
          ),
        ),
      { enableHighAccuracy: true, timeout: timeoutMs, maximumAge: 5_000 },
    );
  });
}

/** Keeps improving the fix while the survey screen is open; returns a stop function. */
export function watchPosition(onFix: (f: Fix) => void, onError: (e: Error) => void): () => void {
  if (!("geolocation" in navigator)) {
    onError(new Error("This device can't share its location"));
    return () => {};
  }
  const id = navigator.geolocation.watchPosition(
    (p) => onFix({ latitude: p.coords.latitude, longitude: p.coords.longitude, accuracy: Math.round(p.coords.accuracy), at: p.timestamp }),
    (e) => onError(new Error(e.code === e.PERMISSION_DENIED ? "Location is off for Arz-e-Pak — allow it in the device settings" : "Waiting for GPS…")),
    { enableHighAccuracy: true, maximumAge: 5_000, timeout: 30_000 },
  );
  return () => navigator.geolocation.clearWatch(id);
}

export const inPakistan = (f: { latitude: number; longitude: number }) => f.latitude >= 23 && f.latitude <= 37.5 && f.longitude >= 60 && f.longitude <= 78;

export function distanceM(a: { latitude: number; longitude: number }, b: { latitude: number; longitude: number }): number {
  const r = (d: number) => (d * Math.PI) / 180;
  const h = Math.sin(r(b.latitude - a.latitude) / 2) ** 2 + Math.cos(r(a.latitude)) * Math.cos(r(b.latitude)) * Math.sin(r(b.longitude - a.longitude) / 2) ** 2;
  return 2 * 6_371_000 * Math.asin(Math.sqrt(h));
}

/** The nearest city to a fix (for pre-filling forms). */
export function nearestCity<T extends { latitude?: number | null; longitude?: number | null }>(fix: Fix, cities: T[]): T | undefined {
  let best: T | undefined;
  let d = Infinity;
  for (const c of cities) {
    if (c.latitude == null || c.longitude == null) continue;
    const x = distanceM(fix, { latitude: c.latitude, longitude: c.longitude });
    if (x < d) {
      d = x;
      best = c;
    }
  }
  return d < 60_000 ? best : undefined;
}

/** Permission check against the signed-in account (mirrors the backend's access rules). */
export function canDo(user: User | null | undefined, permission: string): boolean {
  return !!user && (user.roles?.includes("super_admin") || user.permissions?.includes(permission));
}

/** Phones and tablets have a camera picker on <input capture>; PCs get the webcam window instead. */
export const touchDevice = () => typeof window !== "undefined" && (navigator.maxTouchPoints > 0 || "ontouchstart" in window);
