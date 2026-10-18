import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// Every backend call goes through Vite's proxy (`/api/*` -> `${API_TARGET}/*`), so the
// portal is same-origin in development and needs no CORS set-up. `/media` serves
// uploaded listing photos and `/ads.txt` is the AdSense file Google expects at the root.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const target = env.VITE_API_TARGET || "http://127.0.0.1:8000";
  return {
    plugins: [react()],
    resolve: { alias: { "@": path.resolve(__dirname, "src") } },
    server: {
      port: 5173,
      proxy: {
        "/api": {
          target,
          changeOrigin: true,
          ws: true,
          rewrite: (p) => p.replace(/^\/api/, ""),
        },
        "/media": { target, changeOrigin: true },
        "/ads.txt": { target, changeOrigin: true },
      },
    },
    preview: {
      port: 4173,
      proxy: {
        "/api": { target, changeOrigin: true, ws: true, rewrite: (p) => p.replace(/^\/api/, "") },
        "/media": { target, changeOrigin: true },
        "/ads.txt": { target, changeOrigin: true },
      },
    },
    build: {
      chunkSizeWarningLimit: 1200,
      rollupOptions: {
        output: {
          // Only the libraries themselves go into these chunks. (The object form also pulled in
          // their shared dependencies such as clsx, which made every page load the 400 kB
          // charts chunk and the map chunk.)
          manualChunks(id) {
            if (!id.includes("node_modules")) return undefined;
            // Small helpers shared by the app and the libraries below get their own chunk, so the
            // app doesn't import them from (and preload) the charts chunk.
            if (/node_modules[\/](clsx|tailwind-merge|tiny-invariant|eventemitter3|react-is)[\/]/.test(id)) return "vendor";
            if (/node_modules[\/](react|react-dom|react-router|react-router-dom|scheduler)[\/]/.test(id)) return "react";
            if (/node_modules[\/](recharts|recharts-scale|victory-vendor|d3-[a-z-]+)[\/]/.test(id)) return "charts";
            if (/node_modules[\/](leaflet|react-leaflet|@react-leaflet[\/][a-z-]+)[\/]/.test(id)) return "map";
            if (/node_modules[\/](framer-motion|motion-dom|motion-utils)[\/]/.test(id)) return "motion";
            return undefined;
          },
        },
      },
    },
  };
});
