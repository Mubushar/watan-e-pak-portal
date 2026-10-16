import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "pk.arzepak.app",
  appName: "Arz-e-Pak",
  webDir: "dist",
  backgroundColor: "#f6f8f6",
  android: {
    // Lets a development build talk to an http:// backend on your LAN / emulator host.
    allowMixedContent: true,
  },
  plugins: {
    // Route fetch() through native HTTP: no CORS and no mixed-content blocking on device.
    CapacitorHttp: { enabled: true },
    SplashScreen: {
      launchShowDuration: 1500,
      launchAutoHide: false,
      backgroundColor: "#f6f8f6",
      androidScaleType: "CENTER_CROP",
      showSpinner: false,
    },
    StatusBar: { overlaysWebView: false, style: "LIGHT", backgroundColor: "#f6f8f6" },
    Keyboard: { resize: "body", resizeOnFullScreen: true },
  },
};

export default config;
