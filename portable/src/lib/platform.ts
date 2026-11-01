/** Where the app is running: Android/iOS (Capacitor), desktop (Electron) or a browser. */
import { Capacitor } from "@capacitor/core";

export type Runtime = "android" | "ios" | "desktop" | "web";

export const isNative = Capacitor.isNativePlatform();
export const isElectron = !!window.watanepak?.isElectron || /\bElectron\//.test(navigator.userAgent);

export const runtime: Runtime = isNative ? (Capacitor.getPlatform() as "android" | "ios") : isElectron ? "desktop" : "web";

export const runtimeLabel: Record<Runtime, string> = {
  android: "Android",
  ios: "iOS",
  desktop: window.watanepak?.platform === "darwin" ? "macOS" : window.watanepak?.platform === "win32" ? "Windows" : "Desktop",
  web: "Web",
};
